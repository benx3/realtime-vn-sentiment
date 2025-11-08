"""
Generate complex reviews with longer text and slower rate to observe processing
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
    try:
        db.logs_html.insert_one({
            "ts": datetime.now(),
            "level": level,
            "msg": msg
        })
    except:
        pass  # Ignore log errors
    print(f"[{level}] {msg}")

# Vietnamese complex review templates (much longer and more detailed)
POSITIVE_COMPLEX = [
    "Mình đã mua sản phẩm này từ shop và cảm thấy rất hài lòng. Chất lượng sản phẩm vượt mong đợi, đóng gói rất cẩn thận và kỹ lưỡng. Giao hàng nhanh chóng, shipper thân thiện và chu đáo. Shop tư vấn nhiệt tình, trả lời tin nhắn nhanh. Sản phẩm đúng như mô tả, không có lỗi gì. Giá cả hợp lý so với chất lượng. Mình sẽ tiếp tục ủng hộ shop trong tương lai và giới thiệu cho bạn bè cùng mua.",
    "Đây là lần thứ 3 mình mua hàng ở shop này và lần nào cũng rất ưng ý. Sản phẩm chất lượng cao, giá cả phải chăng. Đóng gói rất kỹ càng, không bị móp méo hay hư hỏng trong quá trình vận chuyển. Shop phục vụ rất chuyên nghiệp, luôn lắng nghe ý kiến khách hàng. Giao hàng đúng hẹn, không bị trễ. Sản phẩm hoạt động tốt, không có vấn đề gì. Rất hài lòng với lần mua sắm này, chắc chắn sẽ quay lại.",
    "Chất lượng sản phẩm xuất sắc, vượt xa mong đợi ban đầu. Mình đã so sánh với nhiều shop khác nhưng shop này vẫn là tốt nhất về cả chất lượng lẫn giá cả. Đóng gói chuyên nghiệp, có hộp riêng và bọc bubble rất cẩn thận. Giao hàng nhanh hơn dự kiến. Shop nhiệt tình tư vấn và giải đáp mọi thắc mắc. Sản phẩm đẹp y hình, màu sắc chuẩn. Chức năng hoạt động mượt mà. Sẽ mua thêm cho gia đình và bạn bè.",
    "Sản phẩm tuyệt vời, đáng đồng tiền bát gạo. Mình đã sử dụng được 2 tuần và không có vấn đề gì. Chất lượng rất tốt, bền bỉ, thiết kế đẹp mắt. Shop giao hàng rất nhanh chỉ trong vòng 2 ngày. Đóng gói cẩn thận, có thêm quà tặng nhỏ rất dễ thương. Nhân viên shop nhiệt tình, hỗ trợ tốt. Giá cả hợp lý, rẻ hơn so với thị trường nhưng chất lượng không hề kém. Rất recommend shop này cho mọi người.",
    "Mình rất hài lòng với sản phẩm và dịch vụ của shop. Đây là sản phẩm chất lượng cao với giá thành phải chăng. Đóng gói rất kỹ càng, sản phẩm được bảo vệ tốt trong quá trình vận chuyển. Giao hàng nhanh chóng và đúng hẹn. Shop phục vụ tận tâm, luôn sẵn sàng giải đáp thắc mắc. Sản phẩm hoạt động tốt, không có lỗi. Thiết kế đẹp, màu sắc như hình. Mình sẽ tiếp tục ủng hộ và giới thiệu cho người thân.",
]

NEGATIVE_COMPLEX = [
    "Mình rất thất vọng với sản phẩm này. Chất lượng không như mô tả, hình ảnh trên shop và thực tế chênh lệch quá nhiều. Sản phẩm bị lỗi ngay từ lần đầu sử dụng. Đóng gói cẩu thả, sản phẩm bị móp méo khi nhận. Mình đã liên hệ với shop nhưng họ không giải quyết thỏa đáng. Giao hàng chậm hơn dự kiến nhiều ngày. Chất liệu kém, không bền. Giá cả không xứng đáng với chất lượng. Mình rất không hài lòng và không recommend cho ai cả.",
    "Sản phẩm tệ, không đúng mô tả. Chất lượng rất kém, trông rẻ tiền. Mình đã đọc review tốt nên mua nhưng thực tế hoàn toàn khác. Đóng gói không cẩn thận, sản phẩm bị trầy xước. Giao hàng trễ, shop không thông báo trước. Khi mình phản ánh thì shop im lặng, không trả lời tin nhắn. Sản phẩm không hoạt động đúng chức năng. Màu sắc khác với hình, kích thước không chuẩn. Rất thất vọng, lần đầu mua hàng mà gặp shop như vậy.",
    "Chất lượng sản phẩm quá tệ so với giá tiền bỏ ra. Mình cảm thấy bị lừa khi mua sản phẩm này. Hình ảnh trên shop rất đẹp nhưng nhận về hoàn toàn khác. Sản phẩm có nhiều lỗi, không thể sử dụng được. Đóng gói dở ẹt, sản phẩm bị vỡ một phần. Giao hàng chậm, shipper thái độ không tốt. Shop không hỗ trợ đổi trả dù sản phẩm lỗi. Mình rất bức xúc và không bao giờ mua hàng ở đây nữa.",
    "Đây là lần mua hàng tệ nhất của mình. Sản phẩm không giống hình, chất lượng kém. Màu sắc bị lỗi, bề mặt không đều. Có mùi hôi khó chịu khi mở hộp. Đóng gói rất tệ, chỉ có một lớp nylon mỏng. Giao hàng chậm hơn 5 ngày so với cam kết. Shop không trả lời tin nhắn khi mình hỏi. Sản phẩm bị lỗi sau 1 ngày sử dụng. Không thể hoàn trả được. Rất thất vọng và tức giận. Không recommend cho ai.",
    "Sản phẩm nhận được không đúng với mô tả của shop. Chất lượng kém, giá cả cao. Đóng gói cẩu thả, không có hộp đựng riêng. Sản phẩm bị trầy xước nhiều vết. Giao hàng trễ mà shop không xin lỗi hay giải thích. Khi nhận được hàng mình phát hiện nhiều lỗi nhưng shop từ chối đổi trả. Thái độ phục vụ rất tệ, không tôn trọng khách hàng. Mình cảm thấy bị lừa đảo. Sẽ không bao giờ quay lại shop này nữa.",
]

NEUTRAL_COMPLEX = [
    "Sản phẩm cũng tạm được, không tốt lắm nhưng cũng không tệ. Chất lượng ở mức trung bình, đúng với giá tiền. Đóng gói bình thường, không có gì đặc biệt. Giao hàng đúng thời gian cam kết. Shop phục vụ bình thường, không có gì nổi bật. Sản phẩm hoạt động ổn, không có lỗi lớn nhưng cũng không xuất sắc. Màu sắc hơi khác so với hình một chút. Nếu cần mua lại mình cũng sẽ cân nhắc thêm.",
    "Nhận được sản phẩm rồi, chất lượng tạm ổn. Không có gì đáng chê nhưng cũng không có gì đáng khen. Đóng gói bình thường, sản phẩm không bị hư hỏng. Giao hàng đúng hẹn. Shop trả lời tin nhắn nhưng không nhiệt tình lắm. Sản phẩm sử dụng được, chức năng cơ bản hoạt động. Giá cả hợp lý với chất lượng. Có thể sẽ mua lại nếu có ưu đãi tốt.",
    "Sản phẩm nhận được đúng như mô tả, không tốt không xấu. Chất lượng trung bình, phù hợp với giá. Đóng gói đơn giản nhưng đủ dùng. Giao hàng trong thời gian dự kiến. Shop phục vụ ổn, không có gì đặc biệt. Sản phẩm hoạt động bình thường, không có lỗi nhưng cũng không có gì nổi bật. Có lẽ sẽ tìm sản phẩm khác lần sau để so sánh.",
    "Mình đã nhận được hàng, sản phẩm cũng được. Chất lượng không xuất sắc nhưng chấp nhận được. Đóng gói bình thường, có một vài vết trầy nhỏ. Giao hàng đúng giờ. Shop trả lời tin nhắn nhưng hơi chậm. Sản phẩm sử dụng tạm ổn, không có vấn đề lớn. Giá cả hợp lý. Nếu có lựa chọn tốt hơn mình sẽ đổi, còn không thì dùng tạm.",
    "Sản phẩm nhận về ở mức khá, không quá tốt cũng không quá tệ. Chất lượng trung bình khá, đúng giá tiền bỏ ra. Đóng gói đơn giản nhưng an toàn. Giao hàng đúng hẹn, không trễ. Shop phục vụ bình thường. Sản phẩm hoạt động ổn định, chưa phát hiện lỗi. Thiết kế bình thường, không có gì đặc biệt. Có thể mua lại nếu không có sự lựa chọn nào tốt hơn.",
]

PRODUCT_CATEGORIES = [
    ("Điện thoại & Phụ kiện", "mobile_gadget"),
    ("Laptop & Máy tính", "computer"),
    ("Thời trang nam", "fashion_men"),
    ("Thời trang nữ", "fashion_women"),
    ("Đồng hồ", "watch"),
    ("Giày dép nam", "shoes_men"),
    ("Giày dép nữ", "shoes_women"),
    ("Túi xách", "bags"),
    ("Mỹ phẩm", "cosmetic"),
    ("Chăm sóc da", "skincare"),
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

def generate_complex_review(index):
    """Generate a single complex review with longer content"""
    # Random rating distribution: 40% positive (4-5), 30% negative (1-2), 30% neutral (3)
    rand = random.random()
    if rand < 0.4:  # Positive
        rating = random.choice([4, 5])
        content = random.choice(POSITIVE_COMPLEX)
        # Add some random variations to make text longer
        if random.random() < 0.5:
            content += f" Mình đã sử dụng sản phẩm được {random.randint(1, 30)} ngày và rất hài lòng. "
        if random.random() < 0.5:
            content += f"Đây là lần thứ {random.randint(1, 5)} mình mua hàng ở shop. "
        title = "Sản phẩm tốt, rất hài lòng"
    elif rand < 0.7:  # Negative
        rating = random.choice([1, 2])
        content = random.choice(NEGATIVE_COMPLEX)
        if random.random() < 0.5:
            content += f" Mình đã đợi {random.randint(3, 10)} ngày mới nhận được hàng. "
        if random.random() < 0.5:
            content += "Thật sự rất thất vọng và bức xúc. "
        title = "Không hài lòng, chất lượng kém"
    else:  # Neutral
        rating = 3
        content = random.choice(NEUTRAL_COMPLEX)
        if random.random() < 0.5:
            content += f" Sản phẩm dùng được {random.randint(1, 7)} ngày thì vẫn ổn. "
        title = "Bình thường, tạm được"
    
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
        "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - random.randint(0, 7776000))),
        "crawled_at": time.time(),
    }

def main():
    total_reviews = 10000  # Increase to 10k for longer processing
    batch_size = 50  # Smaller batch for slower processing
    delay_between_batches = 2  # Add 2 second delay between batches
    
    log_message("INFO", "Complex crawler system initialized")
    log_message("INFO", f"Target: {total_reviews} reviews, batch size: {batch_size}, delay: {delay_between_batches}s")
    
    print(f"\n🚀 Bắt đầu sinh {total_reviews} reviews phức tạp (dữ liệu dài hơn)...")
    print(f"📊 Phân phối: 40% tích cực (4-5⭐), 30% tiêu cực (1-2⭐), 30% trung bình (3⭐)")
    print(f"⏱️  Có delay {delay_between_batches}s giữa các batch để quan sát processing\n")
    
    start_time = time.time()
    reviews_batch = []
    processed = 0
    
    for i in range(1, total_reviews + 1):
        review = generate_complex_review(i)
        reviews_batch.append(review)
        
        # Send to Kafka and MongoDB every batch_size reviews
        if len(reviews_batch) >= batch_size:
            # Send to Kafka first (before MongoDB adds _id)
            for rev in reviews_batch:
                producer.send("reviews_raw", value=rev)
            producer.flush()
            
            # Insert to MongoDB (will add _id field)
            db.reviews_raw.insert_many(reviews_batch)
            
            processed += len(reviews_batch)
            elapsed = time.time() - start_time
            speed = processed / elapsed if elapsed > 0 else 0
            percentage = (processed / total_reviews) * 100
            
            print(f"✅ Đã xử lý: {processed}/{total_reviews} reviews ({percentage:.0f}%) - Tốc độ: {speed:.0f} reviews/giây")
            
            # Log milestones
            if processed % 1000 == 0:
                log_message("INFO", f"Processed {processed}/{total_reviews} reviews ({speed:.0f} reviews/s)")
            
            reviews_batch = []
            
            # Add delay to slow down and observe processing
            time.sleep(delay_between_batches)
    
    # Process remaining reviews
    if reviews_batch:
        # Send to Kafka first
        for rev in reviews_batch:
            producer.send("reviews_raw", value=rev)
        producer.flush()
        
        # Insert to MongoDB
        db.reviews_raw.insert_many(reviews_batch)
        processed += len(reviews_batch)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    avg_speed = total_reviews / elapsed_time if elapsed_time > 0 else 0
    
    log_message("INFO", f"Processed {processed}/{total_reviews} reviews ({avg_speed:.0f} reviews/s)")
    log_message("SUCCESS", f"Completed {total_reviews} reviews in {elapsed_time:.2f}s")
    log_message("INFO", f"Average speed: {avg_speed:.0f} reviews/second")
    log_message("INFO", f"Written to MongoDB: {processed} documents")
    log_message("INFO", f"Sent to Kafka: {processed} messages")
    
    # Summary
    print("\n" + "="*80)
    print("✨ HOÀN THÀNH!")
    print(f"📝 Tổng số reviews sinh ra: {total_reviews}")
    print(f"📏 Độ dài trung bình mỗi review: ~200-400 ký tự (dài gấp 3-4 lần)")
    print(f"💾 Đã ghi vào MongoDB (reviews_raw): {processed}")
    print(f"📨 Đã gửi vào Kafka (reviews_raw): {processed}")
    print(f"⏱️  Thời gian thực hiện: {elapsed_time:.2f} giây")
    print(f"⚡ Tốc độ trung bình: {avg_speed:.0f} reviews/giây")
    print(f"⏰ Delay giữa các batch: {delay_between_batches}s (để dễ quan sát)")
    print(f"\n🔄 Hệ thống đang xử lý (sẽ lâu hơn do text dài):")
    print(f"   - Spark Streaming đang phân tích với ML model (TF-IDF lâu hơn)")
    print(f"   - PhoBERT Consumer đang dự đoán sentiment với GPU (inference lâu hơn)")
    print(f"   - UI Dashboard đang cập nhật real-time tại: http://127.0.0.1:8501")
    print("="*80)

if __name__ == "__main__":
    main()
