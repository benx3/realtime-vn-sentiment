## Use the official PyTorch runtime image that bundles matching CUDA/cuDNN and PyTorch.
FROM pytorch/pytorch:2.9.0-cuda12.6-cudnn9-runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=/app/models/phobert-sentiment-best \
    PORT=5000

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better cache usage
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create model directory
RUN mkdir -p ${MODEL_DIR}

# Expose the port the app runs on
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the application
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]

