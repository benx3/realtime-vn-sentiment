# Use Playwright's official image which already includes browser dependencies
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory if needed
RUN mkdir -p /app/data

# Health check to ensure the service is running
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:${PORT}/health')" || exit 1

# Run with unbuffered output for better logging
CMD ["python", "-u", "shopee_html.py"]
