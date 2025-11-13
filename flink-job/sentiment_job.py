"""
Simplified Flink Job for Vietnamese Sentiment Analysis
Uses basic Kafka consumer approach compatible with container environment
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

# Import ML utilities
try:
    from ml_utils import BaselineMLModel, PhoBERTClient, create_prediction_document
except ImportError:
    logger.warning("⚠️ ML utils not available, using fallback implementations")
    
    class BaselineMLModel:
        def predict(self, texts):
            return [{'predicted_class': 1, 'sentiment': 'neutral', 'confidence': 0.5, 'probabilities': [0.33, 0.34, 0.33]}]
    
    class PhoBERTClient:
        def __init__(self, url): pass
        def predict(self, texts):
            return [{'predicted_class': 1, 'sentiment': 'neutral', 'confidence': 0.5, 'probabilities': [0.33, 0.34, 0.33]}]
    
    def create_prediction_document(review_data, prediction, model_name):
        return {
            "review_id": review_data.get("review_id"),
            "predicted_sentiment": prediction["predicted_class"],
            "sentiment_label": prediction["sentiment"],
            "confidence": prediction["confidence"],
            "model": model_name,
            "timestamp": datetime.now().isoformat()
        }

class BaselineProcessor(ProcessFunction):
    """Process reviews with baseline ML model"""
    
    def __init__(self):
        self.ml_model = None
        
    def open(self, runtime_context):
        """Initialize ML models and state"""
        if self.model_type == "baseline":
            # Initialize TF-IDF + SGD model (like Spark version)
            self.vectorizer = TfidfVectorizer(
                max_features=10000,
                ngram_range=(1, 2),
                stop_words=None  # Vietnamese stop words would be added here
            )
            self.ml_model = SGDClassifier(
                loss='log_loss',  # for probability outputs
                random_state=42,
                warm_start=True
            )
            
            # State for incremental learning
            self.model_state = runtime_context.get_state(
                ValueStateDescriptor("ml_model", Types.PICKLED_BYTE_ARRAY())
            )
            
            # Load existing model if available
            try:
                saved_model = self.model_state.value()
                if saved_model:
                    self.ml_model, self.vectorizer = pickle.loads(saved_model)
                    logger.info("✅ Loaded existing ML model from state")
            except:
                logger.info("🔄 Initializing new ML model")
                
    def process_element(self, review, ctx):
        """Process individual review"""
        try:
            review_data = json.loads(review)
            review_id = review_data.get("review_id")
            content = review_data.get("content", "")
            rating = review_data.get("rating", 3)
            
            if self.model_type == "baseline":
                prediction = self._predict_baseline(review_data, content, rating)
            else:  # phobert
                prediction = self._predict_phobert(review_data, content)
                
            # Output prediction
            yield json.dumps(prediction, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ Error processing review: {e}")
            
    def _predict_baseline(self, review_data, content, rating):
        """Baseline ML prediction (TF-IDF + SGD)"""
        # Weak labeling from rating
        if rating >= 4:
            label = 2  # positive
        elif rating <= 2:
            label = 0  # negative
        else:
            label = 1  # neutral
            
        # Prepare features
        if not content.strip():
            content = "No content"
            
        try:
            # Transform text to features
            if not hasattr(self.vectorizer, 'vocabulary_') or not self.vectorizer.vocabulary_:
                # Initial fit
                X = self.vectorizer.fit_transform([content])
                self.ml_model.fit(X, [label])
            else:
                # Transform with existing vocabulary
                X = self.vectorizer.transform([content])
                
                # Partial fit for incremental learning
                self.ml_model.partial_fit(X, [label])
                
            # Make prediction
            pred_proba = self.ml_model.predict_proba(X)[0]
            predicted_class = self.ml_model.predict(X)[0]
            
            # Save model state periodically
            if hash(review_data.get("review_id", "")) % 100 == 0:
                model_data = pickle.dumps((self.ml_model, self.vectorizer))
                self.model_state.update(model_data)
                
        except Exception as e:
            logger.error(f"❌ ML Error: {e}")
            # Fallback prediction
            pred_proba = [0.33, 0.34, 0.33]
            predicted_class = 1
            
        return {
            "review_id": review_data.get("review_id"),
            "predicted_sentiment": int(predicted_class),
            "sentiment_label": ["negative", "neutral", "positive"][predicted_class],
            "confidence": float(max(pred_proba)),
            "pred_proba_negative": float(pred_proba[0]),
            "pred_proba_neutral": float(pred_proba[1]),
            "pred_proba_positive": float(pred_proba[2]),
            "model": "flink-baseline",
            "timestamp": datetime.now().isoformat(),
            "platform": review_data.get("platform", "tiki"),
            "category_name": review_data.get("category_name", "Unknown"),
            "product_name": review_data.get("product_name", ""),
            "rating": review_data.get("rating", 0)
        }
        
    def _predict_phobert(self, review_data, content):
        """PhoBERT prediction via inference service"""
        try:
            response = requests.post(
                "http://phobert-infer:8001/predict",
                json={"text": content},
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                
                return {
                    "review_id": review_data.get("review_id"),
                    "predicted_sentiment": result.get("predicted_class", 1),
                    "sentiment_label": result.get("sentiment", "neutral"),
                    "confidence": result.get("confidence", 0.5),
                    "pred_proba_negative": result.get("probabilities", [0.33, 0.34, 0.33])[0],
                    "pred_proba_neutral": result.get("probabilities", [0.33, 0.34, 0.33])[1],
                    "pred_proba_positive": result.get("probabilities", [0.33, 0.34, 0.33])[2],
                    "model": "flink-phobert",
                    "timestamp": datetime.now().isoformat(),
                    "platform": review_data.get("platform", "tiki"),
                    "category_name": review_data.get("category_name", "Unknown"),
                    "product_name": review_data.get("product_name", ""),
                    "rating": review_data.get("rating", 0)
                }
            else:
                raise Exception(f"PhoBERT service error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ PhoBERT Error: {e}")
            # Fallback prediction
            return {
                "review_id": review_data.get("review_id"),
                "predicted_sentiment": 1,
                "sentiment_label": "neutral",
                "confidence": 0.5,
                "pred_proba_negative": 0.33,
                "pred_proba_neutral": 0.34,
                "pred_proba_positive": 0.33,
                "model": "flink-phobert-fallback",
                "timestamp": datetime.now().isoformat(),
                "platform": review_data.get("platform", "tiki"),
                "category_name": review_data.get("category_name", "Unknown"),
                "product_name": review_data.get("product_name", ""),
                "rating": review_data.get("rating", 0)
            }

def create_kafka_source(env, topic: str, bootstrap_servers: str):
    """Create Kafka source"""
    properties = {
        'bootstrap.servers': bootstrap_servers,
        'group.id': f'flink-sentiment-{topic}',
        'auto.offset.reset': 'latest'
    }
    
    return FlinkKafkaConsumer(
        topics=[topic],
        deserialization_schema=SimpleStringSchema(),
        properties=properties
    )

def create_mongodb_sink():
    """Create MongoDB sink function"""
    class MongoSink(ProcessFunction):
        def __init__(self):
            self.mongo_client = None
            
        def open(self, runtime_context):
            from pymongo import MongoClient
            self.mongo_client = MongoClient("mongodb://mongo:27017/")
            self.db = self.mongo_client.reviews_db
            self.collection = self.db.reviews_pred
            
        def process_element(self, prediction_json, ctx):
            try:
                prediction = json.loads(prediction_json)
                
                # Upsert to MongoDB
                self.collection.update_one(
                    {"review_id": prediction["review_id"]},
                    {"$set": prediction},
                    upsert=True
                )
                
                logger.info(f"✅ Saved prediction for review {prediction['review_id']}")
                
            except Exception as e:
                logger.error(f"❌ MongoDB error: {e}")
                
    return MongoSink()

def main():
    """Main Flink application"""
    # Create execution environment
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(2)
    
    # Enable checkpointing
    env.enable_checkpointing(30000)  # 30 seconds
    
    logger.info("🚀 Starting Flink Sentiment Analysis Job")
    
    # Kafka configuration
    bootstrap_servers = "kafka:9092"
    
    # Stream 1: Baseline ML (reviews_raw topic)
    baseline_source = create_kafka_source(env, "reviews_raw", bootstrap_servers)
    baseline_stream = env.add_source(baseline_source, "Reviews Raw Source")
    
    baseline_predictions = baseline_stream.process(
        ReviewProcessor("baseline"), 
        "Baseline ML Processor"
    )
    
    # Stream 2: PhoBERT (reviews topic)  
    phobert_source = create_kafka_source(env, "reviews", bootstrap_servers)
    phobert_stream = env.add_source(phobert_source, "Reviews Source")
    
    phobert_predictions = phobert_stream.process(
        ReviewProcessor("phobert"),
        "PhoBERT Processor"
    )
    
    # Union both prediction streams
    all_predictions = baseline_predictions.union(phobert_predictions)
    
    # Sink to MongoDB
    all_predictions.process(create_mongodb_sink(), "MongoDB Sink")
    
    # Execute the job
    logger.info("▶️ Executing Flink job...")
    env.execute("Vietnamese Sentiment Analysis with Flink")

if __name__ == "__main__":
    main()