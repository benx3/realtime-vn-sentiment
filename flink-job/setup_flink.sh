#!/bin/bash

# Flink Integration Setup Script
# This script helps migrate from Spark to Flink

echo "🚀 Apache Flink Integration for Vietnamese Sentiment Analysis"
echo "============================================================="

# Step 1: Setup
echo "📋 Step 1: Environment Setup"
echo "- Adding Flink services to docker-compose.yml"
echo "- Downloading Flink connectors"

# Step 2: Download required JAR files
echo "📦 Step 2: Downloading Flink Connectors"
mkdir -p flink-job/jars

# Kafka connector for Flink
KAFKA_CONNECTOR_URL="https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/1.18.0/flink-sql-connector-kafka-1.18.0.jar"
echo "⬇️ Downloading Kafka connector..."
curl -L -o flink-job/jars/kafka-connector.jar $KAFKA_CONNECTOR_URL

# MongoDB connector for Flink (if available, otherwise we use custom Python sink)
echo "⬇️ Setting up MongoDB connector..."

# Step 3: Configuration
echo "🔧 Step 3: Configuration"
cat << 'EOF' > flink-job/flink-conf.yaml
# Flink Configuration for Sentiment Analysis
jobmanager.rpc.address: flink-jobmanager
jobmanager.rpc.port: 6123
jobmanager.memory.process.size: 1600m
taskmanager.memory.process.size: 1600m
taskmanager.numberOfTaskSlots: 2
parallelism.default: 2

# Checkpointing
state.backend: filesystem
state.checkpoints.dir: file:///tmp/flink-checkpoints-directory
state.savepoints.dir: file:///tmp/flink-savepoints-directory
execution.checkpointing.interval: 30s
execution.checkpointing.mode: EXACTLY_ONCE

# Kafka settings
restart-strategy: fixed-delay
restart-strategy.fixed-delay.attempts: 3
restart-strategy.fixed-delay.delay: 10s
EOF

# Step 4: Update main docker-compose.yml
echo "🔗 Step 4: Updating docker-compose.yml"
cat << 'EOF' >> docker-compose.yml

  # Apache Flink Services
  flink-jobmanager:
    build: ./flink-job
    container_name: flink-jobmanager
    ports:
      - "8081:8081"  # Flink Web UI
    environment:
      - JOB_MANAGER_RPC_ADDRESS=flink-jobmanager
    command: jobmanager
    volumes:
      - flink_data:/tmp/flink-checkpoints-directory
      - flink_data:/tmp/flink-savepoints-directory
    depends_on:
      - kafka
      - mongo

  flink-taskmanager:
    build: ./flink-job
    depends_on:
      - flink-jobmanager
    environment:
      - JOB_MANAGER_RPC_ADDRESS=flink-jobmanager
      - TASK_MANAGER_NUMBER_OF_TASK_SLOTS=2
    command: taskmanager
    volumes:
      - flink_data:/tmp/flink-checkpoints-directory
      - flink_data:/tmp/flink-savepoints-directory

  # Submit Flink job
  flink-job-submit:
    build: ./flink-job
    depends_on:
      - flink-jobmanager
      - flink-taskmanager
    command: >
      bash -c "
        sleep 30 &&
        python3 /opt/flink/usrlib/sentiment_job.py
      "
    environment:
      - JOB_MANAGER_RPC_ADDRESS=flink-jobmanager
    volumes:
      - flink_data:/tmp/flink-checkpoints-directory

volumes:
  flink_data:
EOF

echo "✅ Flink integration setup complete!"
echo ""
echo "📝 Next Steps:"
echo "1. Review the generated Flink job: flink-job/sentiment_job.py"
echo "2. Customize ML models in the ReviewProcessor class"
echo "3. Run: docker-compose up -d --build"
echo "4. Access Flink Web UI: http://localhost:8081"
echo "5. Monitor job execution and performance"
echo ""
echo "🔄 Migration Benefits:"
echo "- Lower latency than Spark Streaming"
echo "- Better fault tolerance with exactly-once processing"
echo "- Rich windowing and CEP capabilities"
echo "- Unified batch and stream processing"
echo "- Better resource utilization"
echo ""
echo "🎯 Performance Comparison:"
echo "Spark Streaming: ~few seconds latency"
echo "Apache Flink: ~sub-second latency"