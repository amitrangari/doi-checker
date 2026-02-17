#!/usr/bin/env python3
"""
Flask web application for DOI and Reference Checker
"""

import os
import io
import sys
import json
import uuid
import queue
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, Response, stream_with_context
from werkzeug.utils import secure_filename
from doi_checker import PDFReferenceExtractor, URLValidator, ReportGenerator

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# Create necessary directories
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)

# Global dict to store log queues for each job
log_queues = {}
processing_status = {}

class LogCapture(io.StringIO):
    """Capture stdout and put into a queue while also logging to container stdout"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def write(self, text):
        if text.strip():
            self.log_queue.put(text)
            # Also write to real stdout for container logs visibility
            sys.__stdout__.write(text)
            sys.__stdout__.flush()
        return len(text)  # Return length of text written
    
    def flush(self):
        """Flush the stream - required for proper output"""
        sys.__stdout__.flush()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/')
def index():
    """Home page with upload form"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and processing"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only PDF files are allowed'}), 400

    # Save uploaded file
    filename = secure_filename(file.filename)
    job_id = str(uuid.uuid4())
    upload_dir = Path(app.config['UPLOAD_FOLDER']) / job_id
    upload_dir.mkdir(exist_ok=True)

    file_path = upload_dir / filename
    file.save(file_path)

    # Get processing options
    enable_search = request.form.get('enable_search') == 'true'
    timeout = int(request.form.get('timeout', 10))
    delay = float(request.form.get('delay', 1.0))

    return jsonify({
        'job_id': job_id,
        'filename': filename,
        'enable_search': enable_search
    })


@app.route('/stream/<job_id>')
def stream_logs(job_id):
    """Stream processing logs using Server-Sent Events"""
    def generate():
        if job_id not in log_queues:
            log_queues[job_id] = queue.Queue()

        log_queue = log_queues[job_id]

        while True:
            try:
                message = log_queue.get(timeout=1)
                yield f"data: {json.dumps({'log': message})}\n\n"

                # Check if processing is complete
                if job_id in processing_status and processing_status[job_id].get('complete'):
                    yield f"data: {json.dumps({'complete': True, 'status': processing_status[job_id]})}\n\n"
                    break

            except queue.Empty:
                # Send keepalive
                yield f"data: {json.dumps({'keepalive': True})}\n\n"

                # Check if processing failed or completed
                if job_id in processing_status:
                    status = processing_status[job_id]
                    if status.get('complete') or status.get('error'):
                        yield f"data: {json.dumps({'complete': True, 'status': status})}\n\n"
                        break

    return Response(stream_with_context(generate()), content_type='text/event-stream')


def process_in_background(job_id, pdf_path, enable_search, timeout, delay):
    """Background task to process PDF"""
    # Create log queue
    if job_id not in log_queues:
        log_queues[job_id] = queue.Queue()

    log_queue = log_queues[job_id]

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = LogCapture(log_queue)

    try:
        log_queue.put("=" * 80 + "\n")
        log_queue.put("DOI AND REFERENCE CHECKER\n")
        log_queue.put("=" * 80 + "\n\n")

        # Extract references
        log_queue.put(f"Extracting text from {pdf_path.name}...\n")
        extractor = PDFReferenceExtractor(str(pdf_path))
        extractor.extract_text()

        log_queue.put("Looking for references section...\n")
        refs_text = extractor.find_references_section()
        if not refs_text:
            processing_status[job_id] = {'complete': True, 'error': 'Could not find references section in PDF'}
            return

        log_queue.put("Parsing individual references...\n")
        references = extractor.parse_references(refs_text)

        if not references:
            processing_status[job_id] = {'complete': True, 'error': 'No references were extracted'}
            return

        log_queue.put(f"\nExtracted {len(references)} references\n\n")

        # Validate URLs
        log_queue.put("=" * 80 + "\n")
        log_queue.put("VALIDATING URLS" + (" AND SEARCHING" if enable_search else "") + "\n")
        log_queue.put("=" * 80 + "\n\n")

        validator = URLValidator(timeout=timeout, delay=delay, enable_search=enable_search)

        total_refs = len(references)
        for i, ref in enumerate(references, 1):
            # Calculate and report progress
            progress_pct = int(30 + (i / total_refs * 60))  # Progress from 30% to 90%
            log_queue.put(f"\n{'=' * 80}\n")
            log_queue.put(f"Progress: {progress_pct}% - Processing reference {i}/{total_refs}\n")
            log_queue.put(f"{'=' * 80}\n")
            
            if ref.urls:
                log_queue.put(f"Validating reference with {len(ref.urls)} URL(s)...\n")
                sys.stdout.flush()  # Force flush before validation
                validator.check_reference(ref)
                sys.stdout.flush()  # Force flush after validation
            elif enable_search:
                log_queue.put(f"No URLs found, searching online...\n")
                sys.stdout.flush()
                validator.check_reference(ref)
                sys.stdout.flush()
            else:
                log_queue.put(f"No URLs found in reference\n")

        # Generate reports
        log_queue.put("\n" + "=" * 80 + "\n")
        log_queue.put("GENERATING REPORTS\n")
        log_queue.put("=" * 80 + "\n\n")

        output_dir = Path(app.config['OUTPUT_FOLDER']) / job_id
        reporter = ReportGenerator(output_dir)
        json_path = reporter.generate_json_report(references)
        text_path = reporter.generate_text_report(references)

        log_queue.put(f"\nJSON report saved to: {json_path}\n")
        log_queue.put(f"Text report saved to: {text_path}\n")

        # Generate HTML report
        generate_html_report(references, output_dir, job_id)
        log_queue.put(f"HTML report saved to: {output_dir / 'references.html'}\n")

        # Load JSON report for response
        with open(json_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        # Generate summary
        total = len(references)
        with_urls = sum(1 for ref in references if ref.urls)
        accessible = sum(1 for ref in references if ref.is_accessible)
        searched = sum(1 for ref in references if ref.search_results and ref.search_results.get('search_performed'))

        summary = {
            'total_references': total,
            'with_urls': with_urls,
            'accessible': accessible,
            'inaccessible': with_urls - accessible,
            'searched': searched
        }

        log_queue.put("\n" + "=" * 80 + "\n")
        log_queue.put("DONE!\n")
        log_queue.put("=" * 80 + "\n")

        processing_status[job_id] = {
            'complete': True,
            'success': True,
            'job_id': job_id,
            'summary': summary,
            'references': report_data
        }

    except Exception as e:
        log_queue.put(f"\nERROR: {str(e)}\n")
        processing_status[job_id] = {'complete': True, 'error': str(e)}

    finally:
        # Restore stdout
        sys.stdout = old_stdout


@app.route('/process/<job_id>', methods=['POST'])
def process_file(job_id):
    """Start processing the uploaded PDF file in background"""
    try:
        # Get parameters
        data = request.get_json() or {}
        enable_search = data.get('enable_search', False)
        timeout = data.get('timeout', 10)
        delay = data.get('delay', 1.0)

        # Find the uploaded file
        upload_dir = Path(app.config['UPLOAD_FOLDER']) / job_id
        pdf_files = list(upload_dir.glob('*.pdf'))

        if not pdf_files:
            return jsonify({'error': 'PDF file not found'}), 404

        pdf_path = pdf_files[0]

        # Start processing in background thread
        processing_status[job_id] = {'complete': False, 'started': True}
        thread = threading.Thread(
            target=process_in_background,
            args=(job_id, pdf_path, enable_search, timeout, delay)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': 'Processing started'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/results/<job_id>')
def view_results(job_id):
    """View results page"""
    output_dir = Path(app.config['OUTPUT_FOLDER']) / job_id
    json_path = output_dir / 'references.json'

    # Check if processing is complete
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        # Generate summary
        total = len(report_data)
        with_urls = sum(1 for ref in report_data if ref.get('urls'))
        accessible = sum(1 for ref in report_data if ref.get('is_accessible'))
        searched = sum(1 for ref in report_data if (ref.get('search_results') or {}).get('search_performed'))

        summary = {
            'total_references': total,
            'with_urls': with_urls,
            'accessible': accessible,
            'inaccessible': with_urls - accessible,
            'searched': searched
        }

        return render_template('results.html',
                             job_id=job_id,
                             summary=summary,
                             references=report_data)
    else:
        # Processing still in progress or not started, return template with empty data
        # The JavaScript will show the processing UI and wait for completion
        return render_template('results.html',
                             job_id=job_id,
                             summary={
                                 'total_references': 0,
                                 'with_urls': 0,
                                 'accessible': 0,
                                 'inaccessible': 0,
                                 'searched': 0
                             },
                             references=[])


def generate_html_report(references, output_dir, job_id):
    """Generate an HTML report"""
    html_path = output_dir / 'references.html'

    # Generate summary
    total = len(references)
    with_urls = sum(1 for ref in references if ref.urls)
    accessible = sum(1 for ref in references if ref.is_accessible)
    searched = sum(1 for ref in references if ref.search_results and ref.search_results.get('search_performed'))

    summary = {
        'total_references': total,
        'with_urls': with_urls,
        'accessible': accessible,
        'inaccessible': with_urls - accessible,
        'searched': searched
    }

    # Use the results template to generate HTML
    # Need to use app context when calling from background thread
    with app.app_context():
        with open(html_path, 'w', encoding='utf-8') as f:
            html_content = render_template('results.html',
                                          job_id=job_id,
                                          summary=summary,
                                          references=[{
                                              'number': i,
                                              'raw_text': ref.raw_text,
                                              'authors': ref.authors,
                                              'title': ref.title,
                                              'year': ref.year,
                                              'doi': ref.doi,
                                              'urls': ref.urls,
                                              'is_accessible': ref.is_accessible,
                                              'validation_results': ref.url_check_results,
                                              'search_results': ref.search_results
                                          } for i, ref in enumerate(references, 1)])
            f.write(html_content)


@app.route('/download/<job_id>/<format>')
def download_report(job_id, format):
    """Download report in specified format"""
    output_dir = Path(app.config['OUTPUT_FOLDER']) / job_id

    if format == 'json':
        file_path = output_dir / 'references.json'
        mimetype = 'application/json'
    elif format == 'txt':
        file_path = output_dir / 'references.txt'
        mimetype = 'text/plain'
    elif format == 'html':
        file_path = output_dir / 'references.html'
        mimetype = 'text/html'
    else:
        return "Invalid format", 400

    if not file_path.exists():
        return "File not found", 404

    return send_file(file_path, mimetype=mimetype, as_attachment=True, download_name=f'references.{format}')


@app.route('/api/status')
def status():
    """API status endpoint"""
    return jsonify({
        'status': 'running',
        'version': '1.0.0'
    })


@app.route('/api/job/<job_id>/status')
def job_status(job_id):
    """Check the processing status of a job"""
    if job_id in processing_status:
        return jsonify(processing_status[job_id])
    
    # Check if results file exists
    output_dir = Path(app.config['OUTPUT_FOLDER']) / job_id
    json_path = output_dir / 'references.json'
    
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        
        total = len(report_data)
        with_urls = sum(1 for ref in report_data if ref.get('urls'))
        accessible = sum(1 for ref in report_data if ref.get('is_accessible'))
        searched = sum(1 for ref in report_data if (ref.get('search_results') or {}).get('search_performed'))
        
        summary = {
            'total_references': total,
            'with_urls': with_urls,
            'accessible': accessible,
            'inaccessible': with_urls - accessible,
            'searched': searched
        }
        
        return jsonify({
            'complete': True,
            'success': True,
            'job_id': job_id,
            'summary': summary,
            'references': report_data
        })
    
    return jsonify({'complete': False, 'started': False}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)
