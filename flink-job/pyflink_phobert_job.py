"""
PyFlink PhoBERT Sentiment Analysis Job
Processes reviews from 'reviews' Kafka topic using PhoBERT transformer model
Submittable to Flink cluster for dashboard visualization
"""

import json
import logging
import os
import requests
from typing import Iterable

from pyflink.common import SimpleStringSchema, WatermarkStrategy
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.datastream.functions import MapFunction, ProcessFunction
from pymongo import MongoClient
from datetime import datetime

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ContentFilterFunction(ProcessFunction):
    """Filter reviews with content > 3 chars"""
    
    def __init__(self):
        self.skip_count = 0
    
    def process_element(self, value, ctx):
        try:
            review = json.loads(value)
            content = review.get('content', '')
            
            if len(content) > 3:
                yield review
            else:
                self.skip_count += 1
                if self.skip_count % 50 == 0:
                    logger.info(f"⏭️ PhoBERT: Skipped {self.skip_count} reviews (content too short)")
        except Exception as e:
            logger.warning(f"⚠️ Error processing review: {e}")


class PhoBERTPredictionFunction(MapFunction):
    """Make PhoBERT predictions via inference service"""
    
    def __init__(self):
        self.phobert_url = None
        self.mongo_client = None
        self.processed_count = 0
    
    def open(self, runtime_context):
        """Initialize PhoBERT service and MongoDB connection"""
        self.phobert_url = os.getenv('PHOBERT_URL', 'http://phobert-infer:5000/predict')
        
        # MongoDB connection
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://mongo:27017/?replicaSet=rs0')
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client.reviews_db
        self.collection = self.db.reviews_pred
        
        logger.info("✅ PhoBERTPredictionFunction initialized")
    
    def map(self, review_data):
        """Process review with PhoBERT and save prediction"""
        try:
            content = review_data.get('content', '')
            title = review_data.get('title', '')
            text = f"{title} {content}"
            
            # Call PhoBERT inference service
            response = requests.post(
                self.phobert_url,
                json={"texts": [text]},  # API expects array of texts
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                # API returns lists for batch processing, take first element
                predicted_class = result.get('pred', [1])[0]
                probabilities = result.get('proba', [[0.33, 0.34, 0.33]])[0]
                
                # Map predicted class to Vietnamese sentiment
                sentiment_map = {0: 'Không tốt', 1: 'Trung bình', 2: 'Tốt'}
                sentiment_vn = sentiment_map.get(predicted_class, 'Trung bình')
            else:
                logger.warning(f"⚠️ PhoBERT service error {response.status_code}")
                # Fallback prediction
                rating = review_data.get('rating', 3)
                if rating >= 4:
                    predicted_class, sentiment_vn, probabilities = 1, 'Tốt', [0.1, 0.8, 0.1]
                elif rating <= 2:
                    predicted_class, sentiment_vn, probabilities = 0, 'Không tốt', [0.8, 0.1, 0.1]
                else:
                    predicted_class, sentiment_vn, probabilities = 2, 'Trung bình', [0.2, 0.2, 0.6]
            
            # Create prediction document
            pred_doc = {
                'review_id': review_data.get('review_id'),
                'platform': review_data.get('platform', 'tiki'),
                'product_id': review_data.get('product_id'),
                'category_id': review_data.get('category_id'),
                'category_name': review_data.get('category_name'),
                'rating': review_data.get('rating'),
                'reviewer_name': review_data.get('reviewer_name', 'Anonymous'),
                'title': title,
                'content': content,
                'text': text,
                'pred_label': predicted_class,
                'pred_label_vn': sentiment_vn,
                'pred_proba_vec': json.dumps(probabilities),
                'model': 'phobert',
                'ts': int(datetime.now().timestamp())
            }
            
            # Save to MongoDB
            self.collection.update_one(
                {'review_id': pred_doc['review_id'], 'model': 'phobert'},
                {'$set': pred_doc},
                upsert=True
            )
            
            self.processed_count += 1
            if self.processed_count % 10 == 0:
                logger.info(f"📊 PhoBERT: Processed {self.processed_count} reviews")
            
            return json.dumps(pred_doc)
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ PhoBERT service connection error: {e}")
            return json.dumps({'error': 'phobert_service_unavailable'})
        except Exception as e:
            logger.error(f"❌ Prediction error: {e}")
            return json.dumps({'error': str(e)})
    
    def close(self):
        """Cleanup"""
        if self.mongo_client:
            self.mongo_client.close()
        logger.info(f"✅ PhoBERT job completed: {self.processed_count} reviews processed")


def create_phobert_job():
    """Create and configure PyFlink PhoBERT job"""
    
    # Environment setup
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(1)
    
    # Kafka configuration
    kafka_bootstrap = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
    
    # Kafka source for reviews topic
    kafka_source = KafkaSource.builder() \
        .set_bootstrap_servers(kafka_bootstrap) \
        .set_topics('reviews') \
        .set_group_id('flink-phobert-pyflink') \
        .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()
    
    # Create datastream
    stream = env.from_source(
        kafka_source,
        WatermarkStrategy.no_watermarks(),
        "Kafka Source - reviews"
    )
    
    # Processing pipeline
    filtered_stream = stream.process(ContentFilterFunction())
    predictions = filtered_stream.map(PhoBERTPredictionFunction())
    
    # Execute
    env.execute("Flink PhoBERT Sentiment Analysis")


if __name__ == '__main__':
    logger.info("🚀 Starting PyFlink PhoBERT Job...")
    create_phobert_job()
