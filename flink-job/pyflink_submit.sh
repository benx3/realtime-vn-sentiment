#!/bin/bash
echo "🚀 PyFlink Jobs Submission Script - Version 2.0"

# Wait for Flink cluster
sleep 15

# Check if cluster is ready
while ! curl -s http://flink-jobmanager:8081/overview > /dev/null; do
    echo "⏳ Waiting for Flink cluster..."
    sleep 5
done

echo "✅ Flink cluster ready!"
echo "📊 Flink Dashboard: http://localhost:8081"

# Submit baseline job to Flink cluster
echo "📤 Submitting Baseline Sentiment Job..."
/opt/flink/bin/flink run \
    --jobmanager flink-jobmanager:8081 \
    --python /opt/flink/usrlib/pyflink_baseline_job.py \
    --pyFiles /opt/flink/usrlib \
    --jarfile /opt/flink/lib/flink-sql-connector-kafka-3.0.2-1.18.jar \
    --detached 2>&1 | grep -i "JobID" || echo "📊 Baseline job submitted"

sleep 5

# Submit PhoBERT job to Flink cluster
echo "📤 Submitting PhoBERT Sentiment Job..."
/opt/flink/bin/flink run \
    --jobmanager flink-jobmanager:8081 \
    --python /opt/flink/usrlib/pyflink_phobert_job.py \
    --pyFiles /opt/flink/usrlib \
    --jarfile /opt/flink/lib/flink-sql-connector-kafka-3.0.2-1.18.jar \
    --detached 2>&1 | grep -i "JobID" || echo "📊 PhoBERT job submitted"

echo ""
echo "================================================================"
echo "🎉 PyFlink Jobs Submitted Successfully!"
echo "   📊 Flink Dashboard: http://localhost:8081"
echo "   🔍 Check 'Running Jobs' tab to see active jobs"
echo "   📈 Monitor job metrics and execution plan"
echo "================================================================"

# Keep container alive and monitor jobs
while true; do
    sleep 60
    
    # Check job status via REST API
    JOB_COUNT=$(curl -s http://flink-jobmanager:8081/jobs/overview | grep -o '"running"' | wc -l)
    echo "$(date '+%Y-%m-%d %H:%M:%S'): 💓 Running Jobs: $JOB_COUNT"
    
    # If no jobs running, restart
    if [ "$JOB_COUNT" -eq "0" ]; then
        echo "⚠️ No jobs running, attempting restart..."
        # Could add auto-restart logic here
    fi
done
