import os, json, time
from datetime import datetime
from kafka import KafkaConsumer
import requests
from pymongo import MongoClient

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP","realtime-vn-sentiment-kafka-1:9092")
TOPIC = os.getenv("KAFKA_TOPIC","reviews")
INFER_URL = os.getenv("INFER_URL","http://phobert-infer:5000/predict")
MONGO_URI = os.getenv("MONGO_URI","mongodb://mongo:27017")
BATCH_SIZE = int(os.getenv("BATCH_SIZE","128"))
MAX_LAT_MS = int(os.getenv("MAX_LATENCY_MS","1500"))

print(f"🚀 Starting PhoBERT consumer...")
print(f"  Kafka Bootstrap: {BOOTSTRAP}")
print(f"  Kafka Topic: {TOPIC}")
print(f"  Infer URL: {INFER_URL}")
print(f"  MongoDB URI: {MONGO_URI}")
print(f"  Batch Size: {BATCH_SIZE}, Max Latency: {MAX_LAT_MS}ms")

mongo = MongoClient(MONGO_URI)
db = mongo["reviews_db"]
print(f"✅ Connected to MongoDB")

print(f"🔌 Connecting to Kafka...")
consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=[BOOTSTRAP],
    group_id="phobert-consumer-group",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    enable_auto_commit=True,
    auto_offset_reset="latest",
)
print(f"✅ Connected to Kafka, listening on topic '{TOPIC}'")

buf = []
last_flush = time.time()

def should_use_phobert(prod_id, cat_id):
    # simple routing: global only
    rule = db.control_configs.find_one({"scope":"global"}) or {"active_model":"both"}
    active = rule.get("active_model","both")
    return active in ("phobert","both")

def label_to_vietnamese(pred_label):
    """Convert numeric label to Vietnamese text"""
    label_map = {
        0: "Không tốt",
        1: "Tốt",
        2: "Trung bình"
    }
    return label_map.get(pred_label, f"Unknown({pred_label})")

while True:
    msg = consumer.poll(timeout_ms=500)
    now = time.time()
    if msg:
        for tp, records in msg.items():
            for rec in records:
                r = rec.value
                if not should_use_phobert(r.get("product_id"), r.get("category_id")):
                    continue
                text = f"{r.get('title','')} {r.get('content','')}".strip()
                if len(text) < 3:
                    continue
                buf.append({
                    "review_id": r.get("review_id"),
                    "prod": r.get("product_id"), 
                    "cat": r.get("category_id"), 
                    "cat_name": r.get("category_name", "Unknown"),
                    "rating": r.get("rating"), 
                    "text": text, 
                    "platform": r.get("platform", "unknown")
                })
    if buf and (len(buf) >= BATCH_SIZE or (now - last_flush)*1000 >= MAX_LAT_MS):
        batch = buf[:BATCH_SIZE]; buf = buf[BATCH_SIZE:]; last_flush = now
        texts = [b["text"] for b in batch]
        try:
            res = requests.post(INFER_URL, json={"texts": texts}, timeout=30).json()
            preds = res.get("pred", []); probas = res.get("proba", [])
        except Exception as e:
            print("infer error:", e); continue
        docs = []
        for i, b in enumerate(batch):
            pred = int(preds[i]) if i < len(preds) else None
            proba = probas[i] if i < len(probas) else None
            docs.append({
                "platform": b["platform"],
                "review_id": b.get("review_id"),
                "product_id": b["prod"],
                "category_id": b["cat"],
                "category_name": b["cat_name"],
                "rating": b["rating"],
                "text": b["text"],  # Save original text/content
                "pred_label": pred,
                "pred_label_vn": label_to_vietnamese(pred) if pred is not None else None,
                "pred_proba_vec": json.dumps(proba, ensure_ascii=False) if proba is not None else None,
                "model": "phobert",
                "ts": datetime.now(),
            })
        if docs:
            # Ensure review_id presence, drop any without id to honor unique index
            docs = [d for d in docs if d.get("review_id")]
            if docs:
                try:
                    db.reviews_pred.insert_many(docs, ordered=False)
                except Exception as e:
                    print("insert_many error:", e)
                    # best-effort upsert to avoid duplicates
                    for d in docs:
                        try:
                            db.reviews_pred.update_one(
                                {"review_id": d["review_id"], "model": d["model"]},
                                {"$set": d}, upsert=True)
                        except Exception as ie:
                            print("upsert error:", ie)
