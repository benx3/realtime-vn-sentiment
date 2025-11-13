"""
Flink Job Submission Script
Submits the Vietnamese Sentiment Analysis job to Flink cluster
"""

import time
import requests
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_flink_cluster(max_attempts=30):
    """Wait for Flink JobManager to be ready"""
    jobmanager_url = "http://flink-jobmanager:8081"
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{jobmanager_url}/overview", timeout=5)
            if response.status_code == 200:
                logger.info("✅ Flink cluster is ready!")
                return True
        except Exception as e:
            logger.info(f"⏳ Waiting for Flink cluster... ({attempt + 1}/{max_attempts}) - {e}")
            time.sleep(2)
    
    logger.error("❌ Flink cluster not ready after maximum attempts")
    return False

def submit_job():
    """Submit the sentiment analysis job"""
    try:
        logger.info("🚀 Starting Flink sentiment analysis job submission...")
        
        # Wait for cluster
        if not wait_for_flink_cluster():
            return False
            
        # Import and run the job directly (PyFlink approach)
        logger.info("📊 Executing sentiment analysis job...")
        
        # Set environment variables for the job
        os.environ['KAFKA_BOOTSTRAP'] = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
        os.environ['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://mongo:27017/?replicaSet=rs0')
        os.environ['PHOBERT_URL'] = os.getenv('PHOBERT_URL', 'http://phobert-infer:5000/predict')
        
        # Import and execute the simplified job
        import sys
        sys.path.append('/opt/flink/usrlib')
        
        # Use the simplified Kafka-based approach
        from simple_sentiment_job import main
        main()
        
        logger.info("✅ Job submitted successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to submit job: {e}")
        return False

if __name__ == "__main__":
    success = submit_job()
    if success:
        logger.info("🎉 Flink sentiment analysis job is running!")
        # Keep the container alive to monitor
        while True:
            time.sleep(60)
            logger.info("📊 Job monitoring - check Flink Web UI at http://localhost:8081")
    else:
        logger.error("💥 Job submission failed!")
        exit(1)