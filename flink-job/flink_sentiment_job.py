"""
Proper Apache Flink Streaming Job for Vietnamese Sentiment Analysis
Uses PyFlink API to create proper Flink streaming job
"""

import os
import json
import logging
import requests
from datetime import datetime
from pyflink.common import Types, WatermarkStrategy, Time
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.functions import MapFunction, ProcessFunction
from pyflink.datastream.state import ValueStateDescriptor
from pyflink.common.typeinfo import Types
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SentimentMapFunction(MapFunction):
    """Process sentiment analysis for incoming reviews"""
    
    def __init__(self, model_type="baseline"):
        self.model_type = model_type
        self.mongo_client = None
        self.phobert_url = "http://phobert-infer:5000/predict"
        
    def open(self, runtime_context):
        """Initialize connections"""
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://mongo:27017/?replicaSet=rs0')
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client.reviews_db
        self.collection = self.db.reviews_pred
        
    def map(self, value):
        """Process each review"""
        try:
            review_data = json.loads(value)
            
            if self.model_type == "phobert":
                prediction = self._predict_phobert(review_data)
            else:
                prediction = self._predict_baseline(review_data)
                
            # Save to MongoDB
            self._save_prediction(review_data, prediction)
            
            return f"Processed {review_data.get('review_id')} with {self.model_type}"
            
        except Exception as e:
            logger.error(f"Error processing review: {e}")
            return f"Error: {str(e)}"
    
    def _predict_phobert(self, review_data):
        """PhoBERT prediction via HTTP call"""
        try:
            response = requests.post(
                self.phobert_url,
                json={"text": review_data.get('content', '')},
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                return {
                    'label': result.get('label'),
                    'confidence': result.get('confidence', 0.5)
                }
        except Exception as e:
            logger.warning(f"PhoBERT service error: {e}")
            
        # Fallback to baseline
        return self._predict_baseline(review_data)
    
    def _predict_baseline(self, review_data):
        """Simple baseline sentiment prediction"""
        content = review_data.get('content', '').lower()
        rating = review_data.get('rating', 3)
        
        # Simple keyword-based approach
        positive_words = ['tốt', 'hay', 'đẹp', 'ok', 'ổn', 'good', 'nice', 'great']
        negative_words = ['tệ', 'kém', 'dở', 'bad', 'poor', 'terrible', 'awful']
        
        pos_count = sum(1 for word in positive_words if word in content)
        neg_count = sum(1 for word in negative_words if word in content)
        
        if rating >= 4 or pos_count > neg_count:
            return {'label': 'POSITIVE', 'confidence': 0.7}
        elif rating <= 2 or neg_count > pos_count:
            return {'label': 'NEGATIVE', 'confidence': 0.7}
        else:
            return {'label': 'NEUTRAL', 'confidence': 0.6}
    
    def _save_prediction(self, review_data, prediction):
        """Save prediction to MongoDB"""
        try:
            doc = {
                'review_id': review_data.get('review_id'),
                'platform': review_data.get('platform'),
                'product_id': review_data.get('product_id'),
                'category_id': review_data.get('category_id'),
                'category_name': review_data.get('category_name'),
                'rating': review_data.get('rating'),
                'text': review_data.get('content'),
                'pred_label': prediction.get('label'),
                'pred_label_vn': self._translate_label(prediction.get('label')),
                'pred_proba_vec': [prediction.get('confidence', 0.5)],
                'model': f"flink-{self.model_type}",
                'ts': datetime.now()
            }
            
            # Upsert by review_id and model
            self.collection.update_one(
                {'review_id': doc['review_id'], 'model': doc['model']},
                {'$set': doc},
                upsert=True
            )
        except Exception as e:
            logger.error(f"MongoDB save error: {e}")
    
    def _translate_label(self, label):
        """Translate English label to Vietnamese"""
        translations = {
            'POSITIVE': 'Tích cực',
            'NEGATIVE': 'Tiêu cực', 
            'NEUTRAL': 'Trung tính'
        }
        return translations.get(label, 'Trung tính')

def create_kafka_source(topic, group_id):
    """Create Kafka source for specific topic"""
    kafka_source = KafkaSource.builder() \
        .set_bootstrap_servers("kafka:9092") \
        .set_topics(topic) \
        .set_group_id(group_id) \
        .set_starting_offsets(KafkaOffsetsInitializer.latest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()
    
    return kafka_source

def main():
    """Main Flink job execution"""
    logger.info("🚀 Starting Flink Sentiment Analysis Job")
    
    # Create streaming environment
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(2)
    
    # Enable checkpointing for fault tolerance
    env.enable_checkpointing(10000)  # 10 seconds
    
    # Create Kafka sources
    phobert_source = create_kafka_source("reviews", "flink-phobert-group")
    baseline_source = create_kafka_source("reviews_raw", "flink-baseline-group")
    
    # Create data streams
    phobert_stream = env.from_source(
        phobert_source,
        WatermarkStrategy.no_watermarks(),
        "PhoBERT Reviews Source"
    )
    
    baseline_stream = env.from_source(
        baseline_source, 
        WatermarkStrategy.no_watermarks(),
        "Baseline Reviews Source"
    )
    
    # Apply sentiment processing
    phobert_results = phobert_stream.map(
        SentimentMapFunction("phobert"),
        output_type=Types.STRING()
    )
    
    baseline_results = baseline_stream.map(
        SentimentMapFunction("baseline"),
        output_type=Types.STRING()
    )
    
    # Print results (for monitoring)
    phobert_results.print("PhoBERT Results")
    baseline_results.print("Baseline Results")
    
    # Execute the job
    logger.info("📊 Submitting Flink job...")
    env.execute("Vietnamese Sentiment Analysis Job")

if __name__ == "__main__":
    main()