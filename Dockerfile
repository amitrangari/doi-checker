# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY doi_checker.py .
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Create necessary directories
RUN mkdir -p uploads outputs

# Expose port 5003
EXPOSE 5003

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Run the application with gunicorn
# Increased timeout to 1800 seconds (30 minutes) for processing large PDFs with many references
# Using 3 workers with 2 threads each to prevent SSE blocking and improve concurrency
CMD ["gunicorn", "--bind", "0.0.0.0:5003", "--workers", "3", "--threads", "2", "--timeout", "1800", "app:app"]
