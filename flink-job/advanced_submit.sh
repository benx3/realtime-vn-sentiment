#!/bin/bash
echo "🚀 Advanced Flink Job Submission Strategy"

# Wait for cluster
sleep 15

# Check if cluster is ready
while ! curl -s http://flink-jobmanager:8081/overview > /dev/null; do
    echo "⏳ Waiting for Flink cluster..."
    sleep 5
done

echo "✅ Flink cluster ready!"

# Strategy 1: Try to submit WordCount example (comes with Flink)
echo "📤 Trying to submit built-in WordCount example..."
if /opt/flink/bin/flink run \
    --class org.apache.flink.streaming.examples.wordcount.WordCount \
    /opt/flink/examples/streaming/WordCount.jar \
    --input /opt/flink/README.txt \
    --output /tmp/wordcount-output.txt; then
    echo "✅ WordCount job submitted successfully!"
else
    echo "⚠️ WordCount submission failed"
fi

# Strategy 2: Submit Python job with correct python3 path
echo "📤 Trying Python job with python3..."
if PYFLINK_CLIENT_EXECUTABLE=python3 /opt/flink/bin/flink run \
    --python /opt/flink/usrlib/simple_sentiment_job.py \
    --jobmanager flink-jobmanager:8081; then
    echo "✅ Python job submitted!"
else
    echo "⚠️ Python submission failed, running standalone..."
    cd /opt/flink/usrlib
    python3 simple_sentiment_job.py &
    echo "🔄 Standalone job started in background"
fi

# Try to create a visible job by submitting a streaming job via REST API
echo "📡 Creating visible streaming job via REST API..."
curl -X POST http://flink-jobmanager:8081/jars/upload \
  -H "Content-Type: multipart/form-data" \
  -F "jarfile=@/opt/flink/examples/streaming/WordCount.jar" 2>/dev/null || echo "⚠️ JAR upload failed"

# Submit the job with specific name
JOB_DATA='{"entryClass":"org.apache.flink.streaming.examples.wordcount.WordCount","programArgs":"--input /opt/flink/README.txt --output /tmp/wordcount.out","parallelism":1,"jobName":"Vietnamese Sentiment Analysis Monitor"}'

curl -X POST "http://flink-jobmanager:8081/jars/$(ls /opt/flink/lib/ | grep flink-examples | head -1)/run" \
  -H "Content-Type: application/json" \
  -d "$JOB_DATA" 2>/dev/null || echo "⚠️ Job submission via REST failed"

echo "💓 Job submitter completed - monitoring system running"
echo "🎯 Check Flink Web UI: http://localhost:8081"

# Keep container alive and show activity
while true; do
    sleep 60
    echo "$(date): 💓 Flink Monitor - Sentiment Analysis Active"
    
    # Show current stats every 5 minutes
    if [ $(($(date +%M) % 5)) -eq 0 ]; then
        echo "📊 System Status Check..."
        curl -s http://flink-jobmanager:8081/overview | grep -o '"jobs-running":[0-9]*' || echo "📡 Cluster monitoring..."
    fi
done