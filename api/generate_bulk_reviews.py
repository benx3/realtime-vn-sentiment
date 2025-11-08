"""
Generate 5000 fake reviews simulating crawler data collection
"""
import random
import time
from pymongo import MongoClient
from kafka import KafkaProducer
import json
import os
from datetime import datetime

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017/?replicaSet=rs0")
mongo = MongoClient(MONGO_URI)
db = mongo["reviews_db"]

# Kafka connection
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BOOTSTRAP],
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8")
)

def log_message(level, msg):
    """Write log to MongoDB logs_html collection"""
    db.logs_html.insert_one({
        "ts": datetime.now(),
        "level": level,
        "msg": msg
    })
    print(f"[{level}] {msg}")

# Vietnamese review templates
POSITIVE_REVIEWS = [
    "Sản phẩm chất lượng tốt, đóng gói cẩn thận",
    "Rất hài lòng với sản phẩm này, sẽ mua lại",
    "Giao hàng nhanh, sản phẩm đẹp như hình",
    "Chất lượng vượt mong đợi, giá hợp lý",
    "Đóng gói cẩn thận, shop nhiệt tình",
    "Sản phẩm đúng mô tả, giá tốt",
    "Mình rất thích sản phẩm này",
    "Chất lượng tuyệt vời, sẽ giới thiệu bạn bè",
    "Giao hàng nhanh chóng, đóng gói kỹ càng",
    "Sản phẩm xứng đáng với giá tiền",
    "Shop phục vụ tốt, sản phẩm chất lượng",
    "Rất ưng ý, sẽ ủng hộ shop lâu dài",
    "Đẹp y hình, chất lượng cao cấp",
    "Giá rẻ mà chất lượng không thua kém",
    "Mua lần 2 rồi, vẫn hài lòng như lần đầu",
]

NEGATIVE_REVIEWS = [
    "Chất lượng tệ, không giống hình",
    "Giao hàng lâu, sản phẩm kém",
    "Đóng gói kém, hàng bị móp méo",
    "Không như mong đợi, sẽ không mua lại",
    "Shop phản hồi chậm, sản phẩm kém",
    "Chất lượng kém so với giá tiền",
    "Hàng nhái, không đúng như quảng cáo",
    "Giao hàng quá lâu, hàng kém chất lượng",
    "Thất vọng về sản phẩm này",
    "Không đáng tiền, chất lượng tồi",
    "Ship lâu quá, hàng đến bị móp",
    "Sản phẩm rẻ tiền nhưng kém chất lượng",
    "Không như hình, thất vọng lắm",
    "Màu sắc không đúng, chất liệu kém",
    "Đóng gói tệ, hàng bị vỡ",
]

NEUTRAL_REVIEWS = [
    "Sản phẩm tạm được, giá hơi cao",
    "Chất lượng bình thường, không có gì đặc biệt",
    "Giá hơi cao nhưng chất lượng OK",
    "Sản phẩm tạm ổn, ship hơi lâu",
    "Không quá tốt cũng không quá tệ",
    "Giá cả hợp lý, chất lượng trung bình",
    "Sản phẩm bình thường, dùng được",
    "Chất lượng OK với mức giá này",
    "Tạm chấp nhận được, không xuất sắc",
    "Giá hơi cao cho chất lượng này",
    "Sản phẩm trung bình, không có gì nổi bật",
    "Dùng tạm được, có thể cải thiện hơn",
    "Giá OK, chất lượng cũng tương ứng",
    "Không đặc biệt lắm nhưng cũng không tệ",
    "Sản phẩm bình thường, giá vừa phải",
]

PRODUCT_CATEGORIES = [
    ("Thời trang nam", "fashion_men"),
    ("Thời trang nữ", "fashion_women"),
    ("Điện thoại & phụ kiện", "mobile_gadget"),
    ("Máy tính & laptop", "computer"),
    ("Đồ gia dụng", "home_appliance"),
    ("Sức khỏe & làm đẹp", "health_beauty"),
    ("Mẹ & bé", "baby_products"),
    ("Thực phẩm & đồ uống", "food_beverage"),
    ("Giày dép", "shoes"),
    ("Đồng hồ", "watches"),
]

SHOP_NAMES = [
    "shop_official_vn",
    "authentic_store",
    "premium_shop",
    "vn_retail_store",
    "trusted_seller",
    "quality_market",
    "best_shop_vn",
    "top_seller_official",
]

def generate_review(index):
    """Generate a single review"""
    # Random rating distribution: 40% positive (4-5), 30% negative (1-2), 30% neutral (3)
    rand = random.random()
    if rand < 0.4:  # Positive
        rating = random.choice([4, 5])
        content = random.choice(POSITIVE_REVIEWS)
        title = "Sản phẩm tốt"
    elif rand < 0.7:  # Negative
        rating = random.choice([1, 2])
        content = random.choice(NEGATIVE_REVIEWS)
        title = "Không hài lòng"
    else:  # Neutral
        rating = 3
        content = random.choice(NEUTRAL_REVIEWS)
        title = "Bình thường"
    
    category_name, category_id = random.choice(PRODUCT_CATEGORIES)
    shop_name = random.choice(SHOP_NAMES)
    product_id = f"PROD{random.randint(100000, 999999)}"
    
    return {
        "platform": "shopee",
        "shop_name": shop_name,
        "product_id": product_id,
        "product_name": f"Sản phẩm {category_name} #{index}",
        "category_id": category_id,
        "category_name": category_name,
        "rating": rating,
        "title": title,
        "content": content,
        "reviewer_name": f"user{random.randint(1000, 9999)}",
        "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - random.randint(0, 7776000))),  # Last 90 days
        "crawled_at": time.time(),
    }

def main():
    total_reviews = 5000
    batch_size = 100
    
    log_message("INFO", "Crawler system initialized")
    log_message("INFO", f"Target: {total_reviews} reviews, batch size: {batch_size}")
    
    print(f"🚀 Bắt đầu sinh {total_reviews} reviews giả lập...")
    print(f"📊 Phân phối: 40% tích cực (4-5⭐), 30% tiêu cực (1-2⭐), 30% trung bình (3⭐)")
    print()
    
    reviews_written_to_mongo = 0
    reviews_sent_to_kafka = 0
    
    start_time = time.time()
    
    for batch_num in range(0, total_reviews, batch_size):
        batch_reviews = []
        
        for i in range(batch_num, min(batch_num + batch_size, total_reviews)):
            review = generate_review(i + 1)
            batch_reviews.append(review)
            
            # Send to Kafka for streaming processing
            producer.send("reviews_raw", value=review)
            reviews_sent_to_kafka += 1
        
        # Write batch to MongoDB (simulating crawler saving data)
        if batch_reviews:
            db.reviews_raw.insert_many(batch_reviews)
            reviews_written_to_mongo += len(batch_reviews)
        
        # Progress update
        progress = min(batch_num + batch_size, total_reviews)
        elapsed = time.time() - start_time
        rate = progress / elapsed if elapsed > 0 else 0
        
        print(f"✅ Đã xử lý: {progress}/{total_reviews} reviews "
              f"({progress*100//total_reviews}%) - "
              f"Tốc độ: {rate:.0f} reviews/giây")
        
        # Log every 1000 reviews
        if progress % 1000 == 0:
            log_message("INFO", f"Processed {progress}/{total_reviews} reviews ({rate:.0f} reviews/s)")
        
        # Small delay to simulate realistic crawling
        time.sleep(0.1)
    
    producer.flush()
    
    elapsed = time.time() - start_time
    avg_rate = total_reviews/elapsed
    
    log_message("SUCCESS", f"Completed {total_reviews} reviews in {elapsed:.2f}s")
    log_message("INFO", f"Average speed: {avg_rate:.0f} reviews/second")
    log_message("INFO", f"Written to MongoDB: {reviews_written_to_mongo} documents")
    log_message("INFO", f"Sent to Kafka: {reviews_sent_to_kafka} messages")
    
    print()
    print("=" * 80)
    print(f"✨ HOÀN THÀNH!")
    print(f"📝 Tổng số reviews sinh ra: {total_reviews}")
    print(f"💾 Đã ghi vào MongoDB (reviews_raw): {reviews_written_to_mongo}")
    print(f"📨 Đã gửi vào Kafka (reviews_raw): {reviews_sent_to_kafka}")
    print(f"⏱️  Thời gian thực hiện: {elapsed:.2f} giây")
    print(f"⚡ Tốc độ trung bình: {avg_rate:.0f} reviews/giây")
    print()
    print("🔄 Hệ thống đang xử lý:")
    print("   - Spark Streaming đang phân tích với ML model")
    print("   - PhoBERT Consumer đang dự đoán sentiment với GPU")
    print("   - UI Dashboard đang cập nhật real-time tại: http://127.0.0.1:8501")
    print("=" * 80)

if __name__ == "__main__":
    main()
