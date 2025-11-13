from kafka import KafkaConsumer, KafkaProducer
import json, os, time
from crawlers.shopee import ShopeeClient

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
shopee = ShopeeClient(rate_per_min=60)

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

    platform = cfg.get("platform","shopee")
    shop_links = cfg.get("shop_links") or []
    max_products = int(cfg.get("max_products", 200))
    days_back = int(cfg.get("days_back", 365))

    print(f"Starting crawler for {platform} with {len(shop_links)} shops")
    
    while running and platform == "shopee":
        for link in shop_links:
            if not running or check_stop_signal():  # Check before starting each link
                print("Stopping crawler - stop signal received")
                break
            
            print(f"Crawling shop: {link}")
            try:
                gen = shopee.crawl_shop_reviews(link, max_products=max_products, days_back=days_back)
                review_count = 0
                for rev in gen:
                    if not running or check_stop_signal():  # Check before sending each review
                        print(f"Stopping crawler after {review_count} reviews")
                        break
                    producer.send("reviews_raw", rev)
                    review_count += 1
                    
                    # Check stop signal every 50 reviews
                    if review_count % 50 == 0 and check_stop_signal():
                        print(f"Stopping crawler after {review_count} reviews")
                        break
                        
                print(f"Completed shop {link}: {review_count} reviews")
            except Exception as e:
                print("crawl error", platform, link, e)
            
            if not running or check_stop_signal():  # Check after each link
                print("Stopping crawler - stop signal received")
                break
            time.sleep(0.2)
    
    print("Crawler stopped")
