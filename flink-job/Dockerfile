# Apache Flink with Python support for ML
FROM flink:1.18.0-scala_2.12-java11

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /opt/flink/usrlib /opt/flink/lib-ext

# Skip Kafka connector download - we'll use Python Kafka client
RUN echo "Using Python Kafka client instead of Flink connector"

# Copy Python requirements and install
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

    # Use default Flink configuration
    # COPY flink-conf.yaml /opt/flink/conf/flink-conf.yaml

# Copy Flink jobs and utilities (only active files)
COPY simple_sentiment_job.py /opt/flink/usrlib/
COPY advanced_submit.sh /opt/flink/usrlib/
COPY dashboard_job.py /opt/flink/usrlib/

# Set working directory
WORKDIR /opt/flink

# Default command (overridden by docker-compose)
CMD ["help"]