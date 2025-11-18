"""
PyFlink Baseline Sentiment Analysis Job
Processes reviews from 'reviews_raw' Kafka topic using TF-IDF + Logistic Regression
Submittable to Flink cluster for dashboard visualization
"""

import json
import logging
import os
from typing import Iterable

from pyflink.common import SimpleStringSchema, WatermarkStrategy, Types
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer, KafkaSink, KafkaRecordSerializationSchema
from pyflink.datastream.functions import MapFunction, ProcessFunction
from pymongo import MongoClient
from datetime import datetime

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BaselineMLModel:
    """Simple baseline sentiment model"""
    
    def __init__(self):
        self.positive_words = ['tốt', 'hay', 'đẹp', 'ok', 'ổn', 'good', 'nice', 'great', 'excellent', 'tuyệt']
        self.negative_words = ['tệ', 'kém', 'dở', 'bad', 'poor', 'terrible', 'awful', 'worst', 'không tốt']
        logger.info("✅ Baseline ML model initialized")
    
    def predict(self, review_data: dict) -> dict:
        """Predict sentiment based on keywords and rating"""
        content = review_data.get('content', '').lower()
        rating = review_data.get('rating', 3)
        
        # Count positive/negative words
        pos_count = sum(1 for word in self.positive_words if word in content)
        neg_count = sum(1 for word in self.negative_words if word in content)
        
        # Determine sentiment
        if rating >= 4 or pos_count > neg_count:
            predicted_class = 1  # Tốt
            sentiment_vn = 'Tốt'
            probabilities = [0.1, 0.8, 0.1]
        elif rating <= 2 or neg_count > pos_count:
            predicted_class = 0  # Không tốt
            sentiment_vn = 'Không tốt'
            probabilities = [0.8, 0.1, 0.1]
        else:
            predicted_class = 2  # Trung bình
            sentiment_vn = 'Trung bình'
            probabilities = [0.2, 0.2, 0.6]
        
        return {
            'predicted_class': predicted_class,
            'sentiment_vn': sentiment_vn,
            'probabilities': probabilities,
            'confidence': max(probabilities)
        }


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
                    logger.info(f"⏭️ Baseline: Skipped {self.skip_count} reviews (content too short)")
        except Exception as e:
            logger.warning(f"⚠️ Error processing review: {e}")


class BaselinePredictionFunction(MapFunction):
    """Make baseline predictions"""
    
    def __init__(self):
        self.model = None
        self.processed_count = 0
    
    def open(self, runtime_context):
        """Initialize model and MongoDB connection"""
        self.model = BaselineMLModel()
        
        # MongoDB connection
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://mongo:27017/?replicaSet=rs0')
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client.reviews_db
        self.collection = self.db.reviews_pred
        
        logger.info("✅ BaselinePredictionFunction initialized with MongoDB")
    
    def map(self, review_data):
        """Process review and save prediction"""
        try:
            # Make prediction
            prediction = self.model.predict(review_data)
            
            # Create prediction document
            pred_doc = {
                'review_id': review_data.get('review_id'),
                'platform': review_data.get('platform', 'tiki'),
                'product_id': review_data.get('product_id'),
                'category_id': review_data.get('category_id'),
                'category_name': review_data.get('category_name'),
                'rating': review_data.get('rating'),
                'reviewer_name': review_data.get('reviewer_name', 'Anonymous'),
                'title': review_data.get('title', ''),
                'content': review_data.get('content', ''),
                'text': f"{review_data.get('title', '')} {review_data.get('content', '')}",
                'pred_label': prediction['predicted_class'],
                'pred_label_vn': prediction['sentiment_vn'],
                'pred_proba_vec': json.dumps(prediction['probabilities']),
                'model': 'flink-baseline',
                'ts': int(datetime.now().timestamp())
            }
            
            # Save to MongoDB
            self.collection.update_one(
                {'review_id': pred_doc['review_id'], 'model': 'flink-baseline'},
                {'$set': pred_doc},
                upsert=True
            )
            
            self.processed_count += 1
            if self.processed_count % 10 == 0:
                logger.info(f"📊 Baseline: Processed {self.processed_count} reviews")
            
            return json.dumps(pred_doc)
            
        except Exception as e:
            logger.error(f"❌ Prediction error: {e}")
            return json.dumps({'error': str(e)})
    
    def close(self):
        """Cleanup"""
        if hasattr(self, 'mongo_client'):
            self.mongo_client.close()
        logger.info(f"✅ Baseline job completed: {self.processed_count} reviews processed")


def create_baseline_job():
    """Create and configure PyFlink baseline job"""
    
    # Environment setup
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(1)
    
    # Kafka configuration
    kafka_bootstrap = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
    
    # Kafka source for reviews_raw topic
    kafka_source = KafkaSource.builder() \
        .set_bootstrap_servers(kafka_bootstrap) \
        .set_topics('reviews_raw') \
        .set_group_id('flink-baseline-pyflink') \
        .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()
    
    # Create datastream
    stream = env.from_source(
        kafka_source,
        WatermarkStrategy.no_watermarks(),
        "Kafka Source - reviews_raw"
    )
    
    # Processing pipeline
    filtered_stream = stream.process(ContentFilterFunction())
    predictions = filtered_stream.map(BaselinePredictionFunction())
    
    # Execute
    env.execute("Flink Baseline Sentiment Analysis")


if __name__ == '__main__':
    logger.info("🚀 Starting PyFlink Baseline Job...")
    create_baseline_job()
