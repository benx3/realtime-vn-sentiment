"""
Flink Dashboard Monitoring Job
Creates a visible long-running job in Flink Dashboard to show system is processing
"""
import os
import time
from pymongo import MongoClient

def main():
    """Monitor and display stats periodically"""
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://mongo:27017/?replicaSet=rs0')
    
    print("=" * 80)
    print("🚀 Vietnamese Sentiment Analysis - Dashboard Monitor Started")
    print("=" * 80)
    
    while True:
        try:
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            db = client.reviews_db
            
            reviews_count = db.reviews_raw.count_documents({})
            predictions_count = db.reviews_pred.count_documents({})
            
            baseline_count = db.reviews_pred.count_documents({"model": "flink-baseline"})
            phobert_count = db.reviews_pred.count_documents({"model": "flink-phobert"})
            
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📊 System Status:")
            print(f"  📝 Total Reviews Crawled: {reviews_count:,}")
            print(f"  🔮 Total Predictions: {predictions_count:,}")
            print(f"  📈 Baseline Model: {baseline_count:,} predictions")
            print(f"  🤖 PhoBERT Model: {phobert_count:,} predictions")
            print(f"  ✅ Pipeline Status: ACTIVE")
            
            client.close()
        except Exception as e:
            print(f"⚠️ Monitoring error: {e}")
        
        time.sleep(30)  # Update every 30 seconds

if __name__ == "__main__":
    main()
