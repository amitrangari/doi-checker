# DOI and Reference Checker for Research Paper Reviewers

A comprehensive tool designed to help research paper reviewers validate references quickly and accurately. This automated system extracts, parses, and validates all references from research papers in PDF format, saving hours of manual verification work.

## Why This Tool Matters for Paper Reviewers

As a research paper reviewer, you know that:
- Verifying dozens of references manually is tedious and time-consuming
- Broken or inaccessible DOIs/URLs indicate poor quality control
- Mismatched references (wrong authors/titles) suggest plagiarism or carelessness
- Finding references without proper citations is difficult
- Cross-referencing titles and authors across multiple sources is error-prone

**This tool automates all of this**, providing you with:
- ✅ Instant validation of all DOIs and URLs (accessible or broken)
- ✅ Content verification (does the URL actually match the reference?)
- ✅ Author and title matching scores
- ✅ Web search for references missing URLs
- ✅ Beautiful, interactive reports you can save and share
- ✅ Real-time processing with live progress updates

## Quick Start

### Option 1: Docker Deployment (Recommended)

The easiest way to run the application - no Python setup needed:

```bash
# Navigate to the directory
cd code/review-papers/doi-checker

# Start the application
docker-compose up -d

# Access the web interface
# Open your browser to: http://localhost:5003
```

To stop:
```bash
docker-compose down
```

To view logs:
```bash
docker-compose logs -f
```

### Option 2: Manual Installation

```bash
# Navigate to the directory
cd code/review-papers/doi-checker

# Install dependencies
pip install -r requirements.txt

# Run the web interface
python app.py

# Or use gunicorn for production
gunicorn --bind 0.0.0.0:5003 --workers 2 --timeout 300 app:app
```

Requirements: Python 3.7 or higher

## How to Use the Tool

### Web Interface (Easiest for Reviewers)

1. **Upload PDF**: Open `http://localhost:5003` and drag & drop your research paper
2. **Configure Options**:
   - Enable web search if you want to find URLs for references without them
   - Adjust timeout/delay if needed (defaults work for most cases)
3. **Process**: Click "Process PDF" and watch real-time progress in the console
4. **Review Results**: 
   - See color-coded status for each reference
   - Review match scores for content verification
   - Identify broken or missing URLs instantly
5. **Download Reports**: Save results as JSON, TXT, or HTML for your records

### Command Line Interface

```bash
# Basic validation of all references
python doi_checker.py paper.pdf

# Fast extraction only (no URL checking)
python doi_checker.py paper.pdf --no-validate

# With web search for missing URLs
python doi_checker.py paper.pdf --enable-search

# For papers with many references (be respectful to servers)
python doi_checker.py paper.pdf --delay 2.0 --timeout 30

# Custom output directory
python doi_checker.py paper.pdf -o my_analysis/
```

### Command Line Options

```
usage: doi_checker.py [-h] [-o OUTPUT_DIR] [--no-validate] [--timeout TIMEOUT]
                      [--delay DELAY] [--enable-search] pdf_file

positional arguments:
  pdf_file              Path to the PDF file

optional arguments:
  -h, --help            Show this help message and exit
  -o OUTPUT_DIR         Output directory (default: output)
  --no-validate         Extract only, skip URL validation (faster)
  --timeout TIMEOUT     URL request timeout in seconds (default: 10)
  --delay DELAY         Delay between requests (default: 1.0)
  --enable-search       Enable web search for missing URLs
```

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Interface (Flask)                     │
│  - File upload handling                                      │
│  - Real-time log streaming (Server-Sent Events)             │
│  - Results visualization                                     │
│  - Multi-format report generation (JSON/TXT/HTML)           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Core Processing Engine                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. PDFReferenceExtractor                            │  │
│  │     - PyPDF2 for text extraction                     │  │
│  │     - Pattern matching for references section        │  │
│  │     - Regex-based parsing (authors, title, DOI, URL)│  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  2. URLValidator                                     │  │
│  │     - HTTP requests with user-agent rotation         │  │
│  │     - Redirect handling (2xx status codes)           │  │
│  │     - BeautifulSoup for content extraction           │  │
│  │     - FuzzyWuzzy for title/author matching           │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  3. WebSearchEngine (Optional)                       │  │
│  │     - DuckDuckGo search API                          │  │
│  │     - Result scoring and ranking                     │  │
│  │     - Content matching with fuzzy logic              │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  4. ReportGenerator                                  │  │
│  │     - JSON (machine-readable)                        │  │
│  │     - TXT (human-readable)                           │  │
│  │     - HTML (interactive, styled)                     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  - uploads/  : Temporary PDF storage                        │
│  - outputs/  : Generated reports (by job ID)                │
└─────────────────────────────────────────────────────────────┘
```

### Processing Flow

1. **PDF Upload**: User uploads PDF via web interface or specifies path in CLI
2. **Text Extraction**: PyPDF2 extracts all text from the PDF
3. **Reference Detection**: Pattern matching finds the "References" or "Bibliography" section
4. **Reference Parsing**: Each reference is parsed using regex patterns to extract:
   - Authors (all listed authors)
   - Title
   - Publication year
   - DOI
   - URLs
5. **URL Validation** (if enabled):
   - For each URL/DOI, HTTP request is made
   - Handles redirects (DOIs often redirect to publisher sites)
   - Extracts content from target page
   - Uses fuzzy matching to compare:
     - Reference title vs. page title (meta tags + HTML parsing)
     - Reference authors vs. page authors
   - Generates match scores (0-100%)
6. **Web Search** (if enabled and no URL found):
   - Searches DuckDuckGo with title + authors
   - Retrieves top results
   - Scores each result based on content similarity
   - Returns best matches
7. **Report Generation**: Creates JSON, TXT, and HTML reports with all findings
8. **Real-time Streaming**: Progress logs streamed to browser via Server-Sent Events (SSE)

### Technology Stack

- **Backend**: Python 3.7+, Flask, Gunicorn
- **PDF Processing**: PyPDF2
- **Web Scraping**: BeautifulSoup4, requests
- **Text Matching**: FuzzyWuzzy (Levenshtein distance)
- **Containerization**: Docker, Docker Compose
- **Frontend**: HTML5, CSS3, JavaScript (vanilla)
- **Real-time Communication**: Server-Sent Events (SSE)

## Features & Usage

### For Research Paper Reviewers

#### 1. Quick Quality Check
```bash
# Get instant overview of reference quality
python doi_checker.py paper.pdf
```
**Reviewers benefit**: Immediately see how many references have broken links or are inaccessible.

#### 2. Content Verification
The tool doesn't just check if URLs work - it verifies they point to the correct paper:
- Title matching (85%+ = good match)
- Author verification (counts how many authors found)
- Flags suspicious mismatches

**Reviewers benefit**: Catch copy-paste errors, placeholder references, or potential plagiarism.

#### 3. Missing URL Detection
```bash
# Find references without URLs using web search
python doi_checker.py paper.pdf --enable-search
```
**Reviewers benefit**: Verify references even when DOIs/URLs are missing.

#### 4. Batch Processing
```bash
# Process multiple papers
for paper in papers/*.pdf; do
    python doi_checker.py "$paper" -o "reviews/$(basename $paper .pdf)"
done
```
**Reviewers benefit**: Review multiple submissions efficiently.

#### 5. Interactive Reports
- HTML reports can be saved and shared with editorial teams
- Color-coded status (green = accessible, red = broken)
- Sortable and filterable results
- Downloadable for permanent records

### Using as a Python Library

```python
from doi_checker import PDFReferenceExtractor, URLValidator, ReportGenerator

# Extract references
extractor = PDFReferenceExtractor("paper.pdf")
extractor.extract_text()
refs_text = extractor.find_references_section()
references = extractor.parse_references(refs_text)

# Validate URLs
validator = URLValidator(timeout=10, delay=1.0)
for ref in references:
    if ref.urls:
        validator.check_reference(ref)

# Generate reports
reporter = ReportGenerator("output")
reporter.generate_json_report(references)
reporter.generate_text_report(references)
reporter.generate_html_report(references)
```

See [example_usage.py](example_usage.py) for more detailed examples.

## Output Reports

### 1. JSON Report (`references.json`)
Machine-readable format with complete data:
```json
[
  {
    "number": 1,
    "authors": ["Smith, J.", "Doe, A."],
    "title": "A Study on Machine Learning",
    "year": "2023",
    "doi": "10.1234/example",
    "urls": ["https://doi.org/10.1234/example"],
    "is_accessible": true,
    "validation_results": {
      "accessible_urls": ["https://doi.org/10.1234/example"],
      "inaccessible_urls": [],
      "match_results": [
        {
          "url": "https://doi.org/10.1234/example",
          "final_url": "https://publisher.com/article/12345",
          "title_match": 95,
          "authors_found": 2,
          "author_matches": ["Smith, J.", "Doe, A."]
        }
      ]
    }
  }
]
```

### 2. Text Report (`references.txt`)
Human-readable summary:
```
================================================================================
REFERENCE VALIDATION REPORT
================================================================================

SUMMARY
Total references: 45
References with URLs: 42 (93.3%)
Accessible URLs: 39 (92.9%)
Inaccessible URLs: 3 (7.1%)

================================================================================
REFERENCE #1
================================================================================
Authors: Smith, J., Doe, A.
Title: A Study on Machine Learning
Year: 2023
DOI: 10.1234/example

URL Validation Results:
  ✓ https://doi.org/10.1234/example
    Status: Accessible (200)
    Final URL: https://publisher.com/article/12345
    Title match: 95%
    Authors found: 2/2

Original text:
Smith, J., & Doe, A. (2023). A Study on Machine Learning. Journal of AI, 10(2), 123-145.
```

### 3. HTML Report (`references.html`)
Interactive, styled report with:
- Color-coded status indicators
- Collapsible reference details
- Match score visualizations
- Exportable format for sharing

## How This Helps Research Paper Reviewers

### Time Savings
- **Manual verification**: ~2-5 minutes per reference × 40 references = **2-3 hours**
- **With this tool**: Upload PDF → **5-10 minutes automated processing**
- **Time saved**: **~2 hours per paper**

### Quality Improvements

#### 1. Catch Issues Reviewers Often Miss
- Broken DOI links (publisher site moved)
- Wrong URLs (copy-paste errors)
- Placeholder references ("to appear", "in press" with no link)
- Format inconsistencies

#### 2. Evidence-Based Reviews
- Quantifiable metrics (85% title match, 38/42 URLs accessible)
- Exportable reports for editorial decisions
- Reproducible validation process

#### 3. Focus on Content
- Spend less time on mechanical checking
- More time evaluating scientific merit
- Confidence in reference quality

### Use Cases for Reviewers

**Scenario 1: Initial Screening**
```bash
python doi_checker.py submitted_paper.pdf --no-validate
```
Quickly check if paper has proper references formatted correctly.

**Scenario 2: Detailed Review**
```bash
python doi_checker.py submitted_paper.pdf --enable-search --delay 2.0
```
Full validation with web search for complete assessment.

**Scenario 3: Post-Revision Check**
```bash
python doi_checker.py revised_paper.pdf
```
Verify authors fixed reference issues from previous review.

**Scenario 4: Editorial Decision Support**

Generate HTML report to share with editorial board showing reference quality metrics.

## Docker Deployment

### Quick Start
```bash
# Start application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop application
docker-compose down
```

### Update to Latest Version
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Configuration
Edit `docker-compose.yml` to change:
- Port mapping (default: 5003)
- Resource limits
- Volume mounts

### Health Check
```bash
curl http://localhost:5003/api/status
# Expected: {"status": "running", "version": "2.0.0"}
```

## Troubleshooting

### Common Issues

**"No references found"**
- Verify PDF has "References" or "Bibliography" section
- Check if PDF text is extractable (not scanned images)
- Some PDFs use unusual section naming

**"URLs timing out"**
- Increase timeout: `--timeout 30`
- Some publishers have slow servers
- Network/firewall issues

**"Too many requests"**
- Increase delay: `--delay 2.0`
- Some sites have strict rate limiting
- Process during off-peak hours

**"Low matching scores"**
- Different publishers format differently
- Tool uses fuzzy matching (not exact)
- Manual verification recommended for critical papers

**"Web search not finding results"**
- DuckDuckGo may rate-limit automated requests
- Try again later or increase delay
- Some papers may not be indexed

**Port already in use**
```bash
# Edit docker-compose.yml and change port:
ports:
  - "5004:5003"  # Change 5004 to any available port
```

### Clean Restart
```bash
# Stop everything
docker-compose down -v

# Remove old images
docker rmi doi-checker

# Rebuild from scratch
docker-compose build --no-cache
docker-compose up -d
```

## Performance Tips

- **Faster processing**: Use `--no-validate` for extraction only
- **Better accuracy**: Enable `--enable-search` for missing URLs  
- **Respectful scraping**: Increase `--delay` for many references
- **Slow networks**: Increase `--timeout` for international publishers

## Limitations

- **PDF Quality**: Extraction quality depends on PDF structure (text-based PDFs only)
- **Reference Formats**: Handles common formats but may miss unusual styles
- **Paywalled Content**: Cannot access content behind paywalls
- **Fuzzy Matching**: Not 100% accurate; manual verification recommended for edge cases
- **Rate Limiting**: Some publishers may block automated requests

## Best Practices for Reviewers

1. **First Pass**: Run with `--no-validate` to see if extraction works
2. **Full Check**: Run complete validation before final review
3. **Save Reports**: Keep HTML reports as part of review documentation
4. **Share Findings**: Use reports to give specific feedback to authors
5. **Batch Processing**: Process all papers in a review batch together
6. **Regular Updates**: Pull latest version for bug fixes and improvements

## Requirements

- Python 3.7 or higher
- PyPDF2
- requests
- BeautifulSoup4
- fuzzywuzzy
- Flask (for web interface)
- gunicorn (for production deployment)

Install all dependencies:
```bash
pip install -r requirements.txt
```

## License

MIT License

## Contributing

Contributions welcome! This tool benefits the entire research community. Please submit issues or pull requests.
