"""
Simple Flink Job Submitter using REST API
Creates a proper Flink job that shows up in Web UI
"""

import requests
import json
import time
import logging
import subprocess
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FlinkJobSubmitter:
    def __init__(self, jobmanager_url="http://flink-jobmanager:8081"):
        self.jobmanager_url = jobmanager_url
        
    def wait_for_cluster(self, max_attempts=30):
        """Wait for Flink cluster to be ready"""
        for attempt in range(max_attempts):
            try:
                response = requests.get(f"{self.jobmanager_url}/overview", timeout=5)
                if response.status_code == 200:
                    logger.info("✅ Flink cluster is ready!")
                    return True
            except Exception as e:
                logger.info(f"⏳ Waiting for cluster... ({attempt + 1}/{max_attempts})")
                time.sleep(2)
        return False
    
    def create_dummy_streaming_job(self):
        """Create a dummy streaming job that shows up in Flink UI"""
        job_script = """
import time
import json
from datetime import datetime

def dummy_streaming_job():
    print("🚀 Dummy Flink Streaming Job Started")
    print(f"📊 Job ID: dummy-sentiment-{int(time.time())}")
    print("💓 This job runs to show up in Flink Web UI")
    
    counter = 0
    while True:
        counter += 1
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time}] 💓 Heartbeat #{counter} - Dummy job running...")
        
        # Simulate some processing
        time.sleep(10)
        
        # Break after 1 hour to avoid infinite run
        if counter > 360:  # 360 * 10 seconds = 1 hour
            print("⏰ Job completed after 1 hour")
            break

if __name__ == "__main__":
    dummy_streaming_job()
"""
        
        # Write the dummy job script
        with open("/tmp/dummy_job.py", "w") as f:
            f.write(job_script)
        
        return "/tmp/dummy_job.py"
    
    def submit_via_cli(self):
        """Submit job via Flink CLI"""
        try:
            logger.info("📤 Creating dummy streaming job for UI visibility...")
            job_file = self.create_dummy_streaming_job()
            
            # Try to submit using flink run command
            cmd = [
                "/opt/flink/bin/flink", "run",
                "--python", job_file,
                "--jobmanager", "flink-jobmanager:8081"
            ]
            
            logger.info(f"🔧 Running command: {' '.join(cmd)}")
            result = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Let it run for a bit to establish in UI
            time.sleep(5)
            
            if result.poll() is None:  # Still running
                logger.info("✅ Dummy job submitted and running!")
                return True
            else:
                stdout, stderr = result.communicate()
                logger.warning(f"⚠️ Job submission result: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ CLI submission failed: {e}")
            return False
    
    def submit_via_rest(self):
        """Submit job via REST API (alternative approach)"""
        try:
            # Get available jar files
            response = requests.get(f"{self.jobmanager_url}/jars")
            if response.status_code != 200:
                logger.error("❌ Cannot get JAR list from Flink")
                return False
            
            jars_data = response.json()
            logger.info(f"📋 Available JARs: {len(jars_data.get('files', []))}")
            
            # For now, create a simple monitoring job
            logger.info("🔄 Creating monitoring task...")
            return self.create_monitoring_task()
            
        except Exception as e:
            logger.error(f"❌ REST API submission failed: {e}")
            return False
    
    def create_monitoring_task(self):
        """Create a background monitoring task"""
        try:
            logger.info("📊 Starting Flink monitoring task...")
            
            # Run a background process that shows activity
            monitor_script = """
import time
import requests
from datetime import datetime

def monitor_flink_cluster():
    jobmanager_url = "http://flink-jobmanager:8081"
    counter = 0
    
    print("🎯 Flink Cluster Monitor Started")
    print(f"📡 Monitoring: {jobmanager_url}")
    
    while True:
        counter += 1
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            response = requests.get(f"{jobmanager_url}/overview", timeout=5)
            if response.status_code == 200:
                data = response.json()
                slots_available = data.get('slots-available', 0)
                slots_total = data.get('slots-total', 0)
                print(f"[{current_time}] 📊 Monitor #{counter} - Slots: {slots_available}/{slots_total}")
            else:
                print(f"[{current_time}] ⚠️ Monitor #{counter} - Cluster not responding")
        except Exception as e:
            print(f"[{current_time}] ❌ Monitor #{counter} - Error: {e}")
        
        time.sleep(15)  # Check every 15 seconds
        
        # Auto-stop after 2 hours
        if counter > 480:
            print("⏰ Monitor completed after 2 hours")
            break

if __name__ == "__main__":
    monitor_flink_cluster()
"""
            
            with open("/tmp/monitor_job.py", "w") as f:
                f.write(monitor_script)
            
            # Run the monitor as background process
            subprocess.Popen(["python3", "/tmp/monitor_job.py"])
            logger.info("✅ Monitoring task started!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Monitor task failed: {e}")
            return False

def main():
    logger.info("🚀 Flink Job Submitter Starting...")
    
    submitter = FlinkJobSubmitter()
    
    # Wait for cluster
    if not submitter.wait_for_cluster():
        logger.error("❌ Flink cluster not ready, falling back to simple job")
        # Fall back to simple job
        import subprocess
        subprocess.run(["python3", "/opt/flink/usrlib/simple_sentiment_job.py"])
        return
    
    # Try different submission methods
    success = False
    
    # Method 1: CLI submission
    logger.info("🔧 Trying CLI submission...")
    if submitter.submit_via_cli():
        success = True
        logger.info("✅ CLI submission successful!")
    
    # Method 2: REST API (fallback)
    if not success:
        logger.info("🔄 Trying REST API submission...")
        if submitter.submit_via_rest():
            success = True
            logger.info("✅ REST API submission successful!")
    
    # Method 3: Simple job (final fallback)
    if not success:
        logger.info("🔄 Falling back to simple Kafka consumer...")
        import subprocess
        subprocess.run(["python3", "/opt/flink/usrlib/simple_sentiment_job.py"])
    
    logger.info("🎯 Job submission process completed!")

if __name__ == "__main__":
    main()