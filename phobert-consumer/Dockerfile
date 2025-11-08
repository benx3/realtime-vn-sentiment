# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Health check to ensure the consumer is running
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD ps aux | grep consumer.py | grep -v grep || exit 1

# Run with unbuffered output for better logging
CMD ["python", "-u", "consumer.py"]
