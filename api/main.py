from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
from kafka import KafkaProducer
import json, os, requests, hashlib
from pymongo import MongoClient
from crawlers.tiki import TikiClient

app = FastAPI()
producer = KafkaProducer(bootstrap_servers=[os.getenv("KAFKA_BOOTSTRAP","kafka:9092")],
                         value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"))
MONGO_URI = os.getenv("MONGO_URI","mongodb://mongo:27017")
INFER_URL = os.getenv("INFER_URL","http://phobert-infer:5000/predict")
client = MongoClient(MONGO_URI)
db = client["reviews_db"]

# Ensure indexes to avoid duplicates and speed up lookups
try:
    db.reviews_raw.create_index("review_id", unique=True, sparse=True)
    db.reviews_pred.create_index([("review_id", 1), ("model", 1)], unique=True, sparse=True)
except Exception as e:
    # Non-fatal if index exists
    print("Index creation warning:", e)

@app.get("/health")
def health():
    return {"status": "ok"}

class CrawlReq(BaseModel):
    platform: str = "shopee"
    shop_links: Optional[List[str]] = None
    product_ids: Optional[List[str]] = None
    category_ids: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    auto_mode: bool = True
    rate_limit_per_min: int = 60
    max_products: int = 200
    days_back: int = 365

@app.post("/crawl/start")
def start_crawl(req: CrawlReq):
    payload = req.dict()
    if payload.get("shop_links"):
        payload["platform"] = "shopee"
    producer.send("crawl_jobs", payload)
    db.system_status.update_one({"_id":"crawler"},{"$set":{"running":True,"cfg":payload}},upsert=True)
    return {"ok": True}

@app.post("/crawl/stop")
def stop_crawl():
    producer.send("crawl_jobs", {"stop": True})
    db.system_status.update_one({"_id":"crawler"},{"$set":{"running":False}},upsert=True)
    return {"ok": True}

class TrainReq(BaseModel):
    max_iter: int = 50
    reg_param: float = 1e-3

@app.post("/train/start")
def start_train(req: TrainReq):
    producer.send("train_jobs", req.dict())
    return {"ok": True}

class ControlReq(BaseModel):
    product_id: Optional[str] = None
    category_id: Optional[str] = None
    active_model: str  # "spark-baseline" | "phobert" | "both"

@app.post("/control/model")
def set_model_control(req: ControlReq):
    key = {k:v for k,v in {"product_id":req.product_id,"category_id":req.category_id}.items() if v}
    db.control_configs.update_one(key or {"scope":"global"}, {"$set":{"active_model":req.active_model}}, upsert=True)
    return {"ok": True}

@app.get("/status")
def status():
    crawler = db.system_status.find_one({"_id":"crawler"}) or {}
    counts = {
        "raw": db.reviews_raw.estimated_document_count(),
        "pred": db.reviews_pred.estimated_document_count(),
    }
    return {"crawler": crawler, "counts": counts}

# HTML crawler controls
class HtmlCrawlReq(BaseModel):
    shop_links: List[str]
    max_products: int = 100
    days_back: int = 365

@app.post("/crawl/html/start")
def start_crawl_html(req: HtmlCrawlReq):
    db.system_status.update_one({"_id":"crawler_html_cfg"}, {"$set": req.dict()}, upsert=True)
    db.system_status.update_one({"_id":"crawler"},{"$set":{"running":True,"mode":"html"}},upsert=True)
    return {"ok": True, "mode": "html"}

@app.post("/crawl/html/pause")
def pause_html():
    db.system_status.update_one({"_id":"crawler_html_ctrl"}, {"$set": {"paused": True}}, upsert=True)
    return {"ok": True, "paused": True}

@app.post("/crawl/html/resume")
def resume_html():
    db.system_status.update_one({"_id":"crawler_html_ctrl"}, {"$set": {"paused": False}}, upsert=True)
    return {"ok": True, "paused": False}

@app.post("/crawl/html/stop")
def stop_html():
    db.system_status.update_one({"_id":"crawler_html_ctrl"}, {"$set": {"stop": True}}, upsert=True)
    return {"ok": True, "stop": True}

# Tiki crawler endpoints
class TikiCrawlReq(BaseModel):
    urls: List[str]  # List of Tiki URLs (brand, store, or category)
    max_products: int = 100
    max_reviews_per_product: int = 100  # Increased to 100
    days_back: int = 365

@app.post("/crawl/tiki/start")
def start_tiki_crawl(req: TikiCrawlReq):
    """Start Tiki crawler for brands, stores, or categories"""
    try:
        
        # Store configuration
        import time
        config = {
            "urls": req.urls,
            "max_products": req.max_products,
            "max_reviews_per_product": req.max_reviews_per_product,
            "days_back": req.days_back,
            "status": "running", 
            "started_at": time.time()
        }
        
        db.system_status.update_one(
            {"_id": "tiki_crawler_cfg"}, 
            {"$set": config}, 
            upsert=True
        )
        
        # Reset stop signal on start
        db.system_status.update_one(
            {"_id": "tiki_crawler_ctrl"}, 
            {"$set": {"stop": False}}, 
            upsert=True
        )
        
        # Start crawling in background
        import threading
        def crawl_tiki():
            tiki = TikiClient(rate_per_min=20)  # Conservative rate limit
            total_reviews = 0
            
            for url in req.urls:
                # Check stop signal before each URL
                ctrl = db.system_status.find_one({"_id": "tiki_crawler_ctrl"}) or {}
                if ctrl.get("stop"):
                    print("🛑 Tiki crawl stopped by user (before URL)")
                    db.system_status.update_one(
                        {"_id": "tiki_crawler_cfg"}, 
                        {"$set": {"status": "stopped", "total_reviews": total_reviews}}, 
                        upsert=True
                    )
                    return
                try:
                    print(f"🚀 Starting Tiki crawl for: {url}")
                    reviews = tiki.crawl_reviews_from_url(
                        url=url,
                        max_products=req.max_products,
                        max_reviews_per_product=req.max_reviews_per_product,
                        days_back=req.days_back
                    )
                    
                    for review in reviews:
                        try:
                            rid = str(review.get('review_id', ''))
                            print(f"📝 Saving review: {rid}")

                            # Upsert into MongoDB by review_id; insert if new, ignore if exists (no duplicate errors)
                            doc = {k: v for k, v in review.items() if k != '_id'}
                            upsert_res = db.reviews_raw.update_one(
                                {"review_id": rid},
                                {"$setOnInsert": doc},
                                upsert=True
                            )
                            is_new = upsert_res.upserted_id is not None
                            if is_new:
                                print(f"✅ Inserted new review with upsert_id: {upsert_res.upserted_id}")
                            else:
                                print(f"ℹ️ Review already exists (review_id={rid}), skipping re-insert")
                            
                            # Send to Kafka - data splitting between models (deterministic 50/50)
                            review_id = rid
                            # Use stable hash (md5) to avoid Python's randomized hash()
                            hmod2 = int(hashlib.md5(review_id.encode('utf-8')).hexdigest(), 16) % 2
                            print(f"🔀 Data Split Debug: review_id={review_id}, md5_mod2={hmod2}")

                            if is_new:
                                if hmod2 == 0:
                                    # Send to Spark baseline (50% of data)
                                    producer.send('reviews_raw', value=review)
                                    print(f"📊 SPARK: {review_id}")
                                else:
                                    # Send to PhoBERT (50% of data) 
                                    producer.send('reviews', value=review)
                                    print(f"🤖 PHOBERT: {review_id}")
                            else:
                                print(f"⏭️ Skipped Kafka publish for duplicate review_id={review_id}")
                            
                            total_reviews += 1
                            
                        except Exception as e:
                            print(f"❌ Error saving review {review.get('review_id', 'unknown')}: {e}")
                            continue
                        
                        # Check for stop signal - every review
                        ctrl = db.system_status.find_one({"_id": "tiki_crawler_ctrl"}) or {}
                        if ctrl.get("stop"):
                            print("🛑 Tiki crawl stopped by user")
                            db.system_status.update_one(
                                {"_id": "tiki_crawler_cfg"}, 
                                {"$set": {"status": "stopped", "total_reviews": total_reviews}}, 
                                upsert=True
                            )
                            return
                    
                    producer.flush()
                    
                except Exception as e:
                    print(f"❌ Error crawling Tiki URL {url}: {e}")
            
            # Update status when done
            db.system_status.update_one(
                {"_id": "tiki_crawler_cfg"}, 
                {"$set": {"status": "completed", "total_reviews": total_reviews}}, 
                upsert=True
            )
            print(f"✅ Tiki crawl completed. Total reviews: {total_reviews}")
        
        thread = threading.Thread(target=crawl_tiki, daemon=True)
        thread.start()
        
        return {"ok": True, "platform": "tiki", "urls": req.urls, "status": "started"}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/crawl/tiki/stop")
def stop_tiki_crawl():
    """Stop Tiki crawler"""
    db.system_status.update_one(
        {"_id": "tiki_crawler_ctrl"}, 
        {"$set": {"stop": True}}, 
        upsert=True
    )
    db.system_status.update_one(
        {"_id": "tiki_crawler_cfg"}, 
        {"$set": {"status": "stopped"}}, 
        upsert=True
    )
    return {"ok": True, "platform": "tiki", "status": "stopped"}

@app.get("/crawl/tiki/status")
def get_tiki_status():
    """Get Tiki crawler status"""
    config = db.system_status.find_one({"_id": "tiki_crawler_cfg"}) or {}
    ctrl = db.system_status.find_one({"_id": "tiki_crawler_ctrl"}) or {}
    
    tiki_count = db.reviews_raw.count_documents({"platform": "tiki"})
    
    return {
        "platform": "tiki",
        "config": config,
        "control": ctrl,
        "reviews_count": tiki_count
    }

# Test endpoint for Tiki API
@app.get("/test/tiki")
async def test_tiki():
    """Test Tiki API connectivity"""
    try:
        client = TikiClient()
        
        # Test direct product reviews first
        product_id = "275220816"  # Huggies product
        reviews = client.get_product_reviews(product_id, limit=3)
        
        # Test search
        products = client.get_products_by_brand("Huggies", limit=3)
        
        return {
            "ok": True,
            "platform": "tiki",
            "test_results": {
                "product_reviews_count": len(reviews),
                "sample_review": reviews[0] if reviews else None,
                "brand_products_count": len(products),
                "sample_product": products[0] if products else None
            }
        }
    except Exception as e:
        return {
            "ok": False,
            "platform": "tiki",
            "error": str(e)
        }
