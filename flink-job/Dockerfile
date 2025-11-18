# Apache Flink with Python support for ML
FROM flink:1.18.0-scala_2.12-java11

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    curl \
    wget \
    && ln -s /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /opt/flink/usrlib /opt/flink/lib-ext

# Download Kafka connector JAR for PyFlink (required for KafkaSource)
RUN wget -P /opt/flink/lib \
    https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.0.2-1.18/flink-sql-connector-kafka-3.0.2-1.18.jar

# Copy Python requirements and install
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

    # Use default Flink configuration
    # COPY flink-conf.yaml /opt/flink/conf/flink-conf.yaml

# Copy Flink jobs and utilities
COPY simple_sentiment_job.py /opt/flink/usrlib/
COPY advanced_submit.sh /opt/flink/usrlib/
COPY dashboard_job.py /opt/flink/usrlib/

# Copy PyFlink V2 jobs (for cluster submission)
COPY pyflink_baseline_job.py /opt/flink/usrlib/
COPY pyflink_phobert_job.py /opt/flink/usrlib/
COPY pyflink_submit.sh /opt/flink/usrlib/

# Make scripts executable
RUN chmod +x /opt/flink/usrlib/*.sh

# Set working directory
WORKDIR /opt/flink

# Default command (overridden by docker-compose)
CMD ["help"]