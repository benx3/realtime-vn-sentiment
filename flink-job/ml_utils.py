"""
Machine Learning Utilities for Flink Job
Includes Vietnamese text processing and ML models
"""

import re
import json
import pickle
import logging
from typing import List, Dict, Any, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
import numpy as np

logger = logging.getLogger(__name__)

class VietnameseTextProcessor:
    """Vietnamese text preprocessing utilities"""
    
    # Vietnamese stop words (basic set)
    STOP_WORDS = {
        'và', 'của', 'có', 'là', 'được', 'một', 'cho', 'với', 'đã', 'sẽ',
        'này', 'đó', 'các', 'những', 'nhiều', 'rất', 'cũng', 'như', 'từ', 'về',
        'trong', 'không', 'hay', 'hoặc', 'nếu', 'khi', 'vì', 'để', 'mà', 'nên',
        'thì', 'đây', 'đấy', 'ở', 'trên', 'dưới', 'giữa', 'sau', 'trước'
    }
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean Vietnamese text"""
        if not text or not text.strip():
            return "no content"
            
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep Vietnamese diacritics
        text = re.sub(r'[^\w\sàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]', ' ', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove stop words
        words = text.split()
        words = [word for word in words if word not in VietnameseTextProcessor.STOP_WORDS]
        
        return ' '.join(words).strip()

class BaselineMLModel:
    """Baseline ML model using TF-IDF + SGD"""
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            sublinear_tf=True
        )
        
        self.classifier = SGDClassifier(
            loss='log_loss',  # for probability outputs
            alpha=0.0001,
            random_state=42,
            warm_start=True,
            class_weight='balanced'
        )
        
        self.is_fitted = False
        self.classes = np.array([0, 1, 2])  # negative, neutral, positive
        
    def weak_label_from_rating(self, rating: int) -> int:
        """Convert star rating to sentiment label"""
        if rating >= 4:
            return 2  # positive
        elif rating <= 2:
            return 0  # negative
        else:
            return 1  # neutral
            
    def fit_or_partial_fit(self, texts: List[str], ratings: List[int]):
        """Fit or partial fit the model"""
        if not texts:
            return
            
        # Clean texts
        cleaned_texts = [VietnameseTextProcessor.clean_text(text) for text in texts]
        
        # Generate weak labels
        labels = [self.weak_label_from_rating(rating) for rating in ratings]
        
        try:
            if not self.is_fitted:
                # Initial fit
                X = self.vectorizer.fit_transform(cleaned_texts)
                self.classifier.fit(X, labels)
                self.is_fitted = True
                logger.info(f"✅ Initial model fit with {len(texts)} samples")
            else:
                # Partial fit for incremental learning
                X = self.vectorizer.transform(cleaned_texts)
                self.classifier.partial_fit(X, labels)
                logger.debug(f"🔄 Partial fit with {len(texts)} samples")
                
        except Exception as e:
            logger.error(f"❌ Model fitting error: {e}")
            
    def predict(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Predict sentiment for texts"""
        if not self.is_fitted:
            # Return neutral predictions if not fitted
            return [{
                'predicted_class': 1,
                'sentiment': 'neutral',
                'confidence': 0.33,
                'probabilities': [0.33, 0.34, 0.33]
            } for _ in texts]
            
        cleaned_texts = [VietnameseTextProcessor.clean_text(text) for text in texts]
        
        try:
            X = self.vectorizer.transform(cleaned_texts)
            predictions = self.classifier.predict(X)
            probabilities = self.classifier.predict_proba(X)
            
            results = []
            for i, (pred, proba) in enumerate(zip(predictions, probabilities)):
                # Ensure probabilities have correct shape
                if len(proba) == 3:
                    proba_list = proba.tolist()
                else:
                    # Handle case where not all classes have been seen
                    proba_list = [0.33, 0.34, 0.33]
                    
                results.append({
                    'predicted_class': int(pred),
                    'sentiment': ['negative', 'neutral', 'positive'][int(pred)],
                    'confidence': float(max(proba_list)),
                    'probabilities': proba_list
                })
                
            return results
            
        except Exception as e:
            logger.error(f"❌ Prediction error: {e}")
            # Return neutral predictions on error
            return [{
                'predicted_class': 1,
                'sentiment': 'neutral',
                'confidence': 0.33,
                'probabilities': [0.33, 0.34, 0.33]
            } for _ in texts]
    
    def save_state(self) -> bytes:
        """Serialize model state"""
        if not self.is_fitted:
            return b''
            
        try:
            state = {
                'vectorizer': self.vectorizer,
                'classifier': self.classifier,
                'is_fitted': self.is_fitted
            }
            return pickle.dumps(state)
        except Exception as e:
            logger.error(f"❌ Save state error: {e}")
            return b''
    
    def load_state(self, state_bytes: bytes) -> bool:
        """Load model state"""
        if not state_bytes:
            return False
            
        try:
            state = pickle.loads(state_bytes)
            self.vectorizer = state['vectorizer']
            self.classifier = state['classifier']
            self.is_fitted = state['is_fitted']
            logger.info("✅ Model state loaded successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Load state error: {e}")
            return False

class PhoBERTClient:
    """Client for PhoBERT inference service"""
    
    def __init__(self, service_url: str, timeout: float = 5.0):
        self.service_url = service_url
        self.timeout = timeout
        
    def predict(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Get predictions from PhoBERT service"""
        import requests
        
        results = []
        
        for text in texts:
            try:
                response = requests.post(
                    self.service_url,
                    json={"text": text},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    results.append({
                        'predicted_class': result.get('predicted_class', 1),
                        'sentiment': result.get('sentiment', 'neutral'),
                        'confidence': result.get('confidence', 0.5),
                        'probabilities': result.get('probabilities', [0.33, 0.34, 0.33])
                    })
                else:
                    logger.warning(f"⚠️ PhoBERT service error {response.status_code}")
                    results.append(self._fallback_prediction())
                    
            except requests.exceptions.Timeout:
                logger.warning("⏰ PhoBERT service timeout")
                results.append(self._fallback_prediction())
            except Exception as e:
                logger.error(f"❌ PhoBERT service error: {e}")
                results.append(self._fallback_prediction())
                
        return results
    
    def _fallback_prediction(self) -> Dict[str, Any]:
        """Fallback prediction when service fails"""
        return {
            'predicted_class': 1,
            'sentiment': 'neutral',
            'confidence': 0.33,
            'probabilities': [0.33, 0.34, 0.33]
        }

def create_prediction_document(review_data: Dict[str, Any], 
                             prediction: Dict[str, Any], 
                             model_name: str) -> Dict[str, Any]:
    """Create prediction document for MongoDB"""
    from datetime import datetime
    
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
        "processing_time": datetime.now().isoformat()
    }