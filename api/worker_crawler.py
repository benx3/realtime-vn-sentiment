from kafka import KafkaConsumer, KafkaProducer
import json, os, time
from crawlers.shopee import ShopeeClient

BOOT = os.getenv("KAFKA_BOOTSTRAP","kafka:9092")
producer = KafkaProducer(bootstrap_servers=[BOOT], value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"))
consumer = KafkaConsumer("crawl_jobs", bootstrap_servers=[BOOT], value_deserializer=lambda m: json.loads(m.decode("utf-8")))

shopee = ShopeeClient(rate_per_min=60)

running = False
cfg = {}
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

    while running and platform == "shopee":
        for link in shop_links:
            try:
                gen = shopee.crawl_shop_reviews(link, max_products=max_products, days_back=days_back)
                for rev in gen:
                    producer.send("reviews_raw", rev)
            except Exception as e:
                print("crawl error", platform, link, e)
            time.sleep(0.2)
