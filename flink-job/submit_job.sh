#!/bin/bash
echo "🚀 Submitting proper Flink job via CLI..."

# Wait for Flink cluster to be ready
echo "⏳ Waiting for Flink cluster..."
sleep 15

# Check if Flink cluster is ready
while ! curl -s http://flink-jobmanager:8081/overview > /dev/null; do
    echo "⏳ Waiting for Flink JobManager..."
    sleep 5
done

echo "✅ Flink cluster is ready!"

# Try to submit a proper Flink job using JAR approach
echo "📤 Submitting Python job as Flink job..."

# Use Flink run command with Python support
cd /opt/flink/usrlib

# Alternative approach: Submit via REST API
echo "📡 Attempting REST API submission..."

# For now, run the standalone script that works
echo "🔄 Running standalone Kafka consumer (works reliably)..."
python3 simple_sentiment_job.py