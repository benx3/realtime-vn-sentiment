from kafka import KafkaConsumer, KafkaProducer
import json, os, time
from crawlers.tiki import TikiClient

BOOT = os.getenv("KAFKA_BOOTSTRAP","kafka:9092")

# Initialize with retry logic
def init_kafka():
    for i in range(30):  # Try for 30 seconds
        try:
            producer = KafkaProducer(bootstrap_servers=[BOOT], value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"))
            consumer = KafkaConsumer("crawl_jobs", bootstrap_servers=[BOOT], 
                                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                                    consumer_timeout_ms=1000)
            print(f"✅ Connected to Kafka at {BOOT}")
            return producer, consumer
        except Exception as e:
            print(f"⏳ Waiting for Kafka... ({i+1}/30) Error: {e}")
            time.sleep(1)
    raise Exception("❌ Failed to connect to Kafka after 30 attempts")

producer, consumer = init_kafka()
tiki = TikiClient(rate_per_min=60)

running = False
cfg = {}

def check_stop_signal():
    """Check for stop signal from Kafka"""
    global running
    try:
        msg = next(consumer, None)
        if msg and msg.value.get("stop"):
            running = False
            print("🛑 Received stop signal")
            return True
    except:
        pass
    return False

print("🚀 Worker crawler started, waiting for jobs...")

for msg in consumer:
    job = msg.value
    if job.get("stop"):
        running = False
        continue
    running = True
    cfg.update(job)

    platform = cfg.get("platform","tiki")
    shop_links = cfg.get("shop_links") or []
    max_products = int(cfg.get("max_products", 200))
    days_back = int(cfg.get("days_back", 365))

    print(f"Starting crawler for {platform} with {len(shop_links)} shops")
    
    # Only support Tiki platform now (Shopee removed)
    if platform == "tiki":
        print(f"⚠️ Tiki crawler not implemented in worker. Use API endpoints instead.")
    else:
        print(f"❌ Platform {platform} not supported. Only 'tiki' is available.")
    
    print("Crawler stopped")
