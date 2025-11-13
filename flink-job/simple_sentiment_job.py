"""
Simplified Kafka-based Sentiment Analysis Job for Flink Container
Replaces complex PyFlink API with basic Kafka consumers that work reliably
"""

import json
import logging
import os
import time
import threading
from datetime import datetime
from kafka import KafkaConsumer
from pymongo import MongoClient
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SentimentProcessor:
    """Unified sentiment processing for both streams"""
    
    def __init__(self):
        # MongoDB connection
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://mongo:27017/?replicaSet=rs0')
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client.reviews_db
        self.collection = self.db.reviews_pred
        
        # PhoBERT service
        self.phobert_url = os.getenv('PHOBERT_URL', 'http://phobert-infer:5000/predict')
        
        # Baseline ML (simplified)
        self.baseline_model = self._init_baseline_model()
        
        logger.info("✅ SentimentProcessor initialized")
        
    def _init_baseline_model(self):
        """Initialize simple baseline model"""
        return {
            'positive_words': ['tốt', 'hay', 'đẹp', 'ok', 'ổn', 'good', 'nice', 'great', 'excellent'],
            'negative_words': ['tệ', 'kém', 'dở', 'bad', 'poor', 'terrible', 'awful', 'worst']
        }
    
    def predict_baseline(self, review_data):
        """Simple baseline prediction based on keywords"""
        content = review_data.get('content', '').lower()
        rating = review_data.get('rating', 3)
        
        # Count positive/negative words
        pos_count = sum(1 for word in self.baseline_model['positive_words'] if word in content)
        neg_count = sum(1 for word in self.baseline_model['negative_words'] if word in content)
        
        # Combine with rating
        if rating >= 4 or pos_count > neg_count:
            predicted_class = 2  # positive
            sentiment = 'positive'
            probabilities = [0.1, 0.3, 0.6]
        elif rating <= 2 or neg_count > pos_count:
            predicted_class = 0  # negative  
            sentiment = 'negative'
            probabilities = [0.6, 0.3, 0.1]
        else:
            predicted_class = 1  # neutral
            sentiment = 'neutral'
            probabilities = [0.25, 0.5, 0.25]
            
        return {
            'predicted_class': predicted_class,
            'sentiment': sentiment,
            'confidence': max(probabilities),
            'probabilities': probabilities
        }
    
    def predict_phobert(self, review_data):
        """PhoBERT prediction via service call"""
        content = review_data.get('content', '')
        
        try:
            response = requests.post(
                self.phobert_url,
                json={"text": content},
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'predicted_class': result.get('predicted_class', 1),
                    'sentiment': result.get('sentiment', 'neutral'),
                    'confidence': result.get('confidence', 0.5),
                    'probabilities': result.get('probabilities', [0.33, 0.34, 0.33])
                }
            else:
                logger.warning(f"⚠️ PhoBERT service error {response.status_code}")
                
        except Exception as e:
            logger.warning(f"⚠️ PhoBERT service error: {e}")
            
        # Fallback prediction
        return {
            'predicted_class': 1,
            'sentiment': 'neutral', 
            'confidence': 0.33,
            'probabilities': [0.33, 0.34, 0.33]
        }
    
    def create_prediction_doc(self, review_data, prediction, model_name):
        """Create MongoDB document"""
        return {
            "review_id": review_data.get("review_id"),
            "predicted_sentiment": prediction["predicted_class"], 
            "sentiment_label": prediction["sentiment"],
            "confidence": prediction["confidence"],
            "pred_proba_negative": prediction["probabilities"][0],
            "pred_proba_neutral": prediction["probabilities"][1], 
            "pred_proba_positive": prediction["probabilities"][2],
            "model": model_name,
            "timestamp": datetime.now().isoformat(),
            "platform": review_data.get("platform", "unknown"),
            "category_name": review_data.get("category_name", "Unknown"),
            "product_name": review_data.get("product_name", ""),
            "rating": review_data.get("rating", 0),
            "content_length": len(review_data.get("content", "")),
            "flink_processed": True
        }
    
    def save_prediction(self, prediction_doc):
        """Save to MongoDB"""
        try:
            self.collection.update_one(
                {"review_id": prediction_doc["review_id"]},
                {"$set": prediction_doc},
                upsert=True
            )
            logger.debug(f"✅ Saved prediction for review {prediction_doc['review_id']}")
            return True
        except Exception as e:
            logger.error(f"❌ MongoDB save error: {e}")
            return False

class KafkaStreamProcessor:
    """Kafka stream processor"""
    
    def __init__(self, topic, model_type):
        self.topic = topic
        self.model_type = model_type
        self.processor = SentimentProcessor()
        self.running = True
        
        # Kafka consumer
        bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=[bootstrap_servers],
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            group_id=f'flink-{model_type}-consumer'
        )
        
        logger.info(f"🚀 KafkaStreamProcessor initialized for {topic} -> {model_type}")
    
    def start(self):
        """Start processing messages"""
        logger.info(f"▶️ Starting {self.model_type} stream processor...")
        processed_count = 0
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                    
                review_data = message.value
                
                # Make prediction
                if self.model_type == 'baseline':
                    prediction = self.processor.predict_baseline(review_data)
                    model_name = 'flink-baseline'
                else:  # phobert
                    prediction = self.processor.predict_phobert(review_data)
                    model_name = 'flink-phobert'
                
                # Create and save document
                doc = self.processor.create_prediction_doc(review_data, prediction, model_name)
                success = self.processor.save_prediction(doc)
                
                if success:
                    processed_count += 1
                    if processed_count % 10 == 0:
                        logger.info(f"📊 {self.model_type}: Processed {processed_count} reviews")
                        
        except KeyboardInterrupt:
            logger.info(f"⏹️ {self.model_type} processor stopped by user")
        except Exception as e:
            logger.error(f"❌ {self.model_type} processor error: {e}")
        finally:
            self.consumer.close()
            logger.info(f"🏁 {self.model_type} processor finished. Total: {processed_count}")
    
    def stop(self):
        """Stop processing"""
        self.running = False

def wait_for_services():
    """Wait for Kafka and MongoDB to be ready"""
    logger.info("⏳ Waiting for services to be ready...")
    
    # Wait for Kafka
    kafka_ready = False
    for i in range(30):
        try:
            from kafka import KafkaConsumer
            consumer = KafkaConsumer(bootstrap_servers=['kafka:9092'])
            consumer.close()
            kafka_ready = True
            logger.info("✅ Kafka is ready")
            break
        except Exception as e:
            logger.info(f"⏳ Waiting for Kafka... ({i+1}/30)")
            time.sleep(2)
    
    if not kafka_ready:
        logger.error("❌ Kafka not ready after 60 seconds")
        return False
    
    # Wait for MongoDB
    mongo_ready = False
    for i in range(30):
        try:
            mongo_uri = os.getenv('MONGO_URI', 'mongodb://mongo:27017/?replicaSet=rs0')
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            client.close()
            mongo_ready = True
            logger.info("✅ MongoDB is ready")
            break
        except Exception as e:
            logger.info(f"⏳ Waiting for MongoDB... ({i+1}/30)")
            time.sleep(2)
    
    if not mongo_ready:
        logger.error("❌ MongoDB not ready after 60 seconds")
        return False
        
    return True

def main():
    """Main Flink job"""
    logger.info("🚀 Starting Flink Vietnamese Sentiment Analysis Job")
    
    # Wait for services
    if not wait_for_services():
        logger.error("💥 Services not ready, exiting")
        return
    
    # Create stream processors
    baseline_processor = KafkaStreamProcessor('reviews_raw', 'baseline')
    phobert_processor = KafkaStreamProcessor('reviews', 'phobert')
    
    # Start processors in separate threads
    baseline_thread = threading.Thread(target=baseline_processor.start, daemon=True)
    phobert_thread = threading.Thread(target=phobert_processor.start, daemon=True)
    
    baseline_thread.start()
    phobert_thread.start()
    
    logger.info("✅ Both stream processors started")
    logger.info("📊 Processing reviews from Kafka topics:")
    logger.info("   - reviews_raw → flink-baseline model")
    logger.info("   - reviews → flink-phobert model")
    logger.info("🌐 Monitor progress in MongoDB reviews_pred collection")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(30)
            logger.info("💓 Flink sentiment job is running...")
            
            # Check if threads are still alive
            if not baseline_thread.is_alive():
                logger.warning("⚠️ Baseline thread died, restarting...")
                baseline_processor = KafkaStreamProcessor('reviews_raw', 'baseline')
                baseline_thread = threading.Thread(target=baseline_processor.start, daemon=True)
                baseline_thread.start()
                
            if not phobert_thread.is_alive():
                logger.warning("⚠️ PhoBERT thread died, restarting...")
                phobert_processor = KafkaStreamProcessor('reviews', 'phobert')
                phobert_thread = threading.Thread(target=phobert_processor.start, daemon=True)
                phobert_thread.start()
                
    except KeyboardInterrupt:
        logger.info("⏹️ Shutting down Flink job...")
        baseline_processor.stop()
        phobert_processor.stop()
        
    logger.info("🏁 Flink Vietnamese Sentiment Analysis Job finished")

if __name__ == "__main__":
    main()