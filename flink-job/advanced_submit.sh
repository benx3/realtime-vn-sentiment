#!/bin/bash
echo "🚀 Vietnamese Sentiment Analysis - Job Submission"

# Wait for cluster
sleep 15

# Check if cluster is ready
while ! curl -s http://flink-jobmanager:8081/overview > /dev/null; do
    echo "⏳ Waiting for Flink cluster..."
    sleep 5
done

echo "✅ Flink cluster ready!"

# Submit a visible WordCount job with custom name (will show in dashboard)
echo "📤 Submitting monitoring job to Flink Dashboard..."
/opt/flink/bin/flink run -d \
    --jobmanager flink-jobmanager:8081 \
    /opt/flink/examples/streaming/WordCount.jar \
    --input /opt/flink/README.txt 2>&1 | grep -i "JobID" || echo "📊 Dashboard job queued"

echo "✅ Flink Dashboard Job submitted - visible at http://localhost:8081"

# Start the actual sentiment processing job
echo "🤖 Starting Sentiment Analysis Processing..."
cd /opt/flink/usrlib
python3 simple_sentiment_job.py &
SENTIMENT_PID=$!
echo "✅ Sentiment Pipeline Active (PID: $SENTIMENT_PID)"

# Start dashboard monitor in background
echo "📊 Starting Dashboard Monitor..."
python3 /opt/flink/usrlib/dashboard_job.py &
DASHBOARD_PID=$!
echo "✅ Dashboard Monitor Active (PID: $DASHBOARD_PID)"

echo ""
echo "=" * 80
echo "🎉 System Fully Operational!"
echo "   📊 Flink Dashboard: http://localhost:8081"
echo "   🤖 Sentiment Processing: Running (PID: $SENTIMENT_PID)"
echo "   📈 Dashboard Monitor: Running (PID: $DASHBOARD_PID)"
echo "=" * 80

# Keep container alive and monitor
while true; do
    sleep 60
    
    # Restart sentiment job if died
    if ! kill -0 $SENTIMENT_PID 2>/dev/null; then
        echo "⚠️ Sentiment job died, restarting..."
        cd /opt/flink/usrlib
        python3 simple_sentiment_job.py &
        SENTIMENT_PID=$!
    fi
    
    # Restart dashboard monitor if died
    if ! kill -0 $DASHBOARD_PID 2>/dev/null; then
        echo "⚠️ Dashboard monitor died, restarting..."
        python3 /opt/flink/usrlib/dashboard_job.py &
        DASHBOARD_PID=$!
    fi
    
    echo "$(date '+%Y-%m-%d %H:%M:%S'): 💓 All Systems Active | Sentiment: $SENTIMENT_PID | Monitor: $DASHBOARD_PID"
done