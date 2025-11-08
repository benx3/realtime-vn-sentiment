# BÁO CÁO DỰ ÁN: HỆ THỐNG PHÂN TÍCH CẢM XÚC SẢN PHẨM TIẾNG VIỆT THỜI GIAN THỰC

Tác giả: ..................................
Lớp/Môn: ..................................
Ngày: 08/11/2025

---

## Lời mở đầu

Trong bối cảnh thương mại điện tử phát triển mạnh mẽ, việc nắm bắt cảm nhận của khách hàng theo thời gian thực giúp doanh nghiệp phản ứng nhanh với vấn đề và tối ưu chiến lược sản phẩm. Báo cáo này trình bày một hệ thống phân tích cảm xúc (sentiment analysis) tiếng Việt theo thời gian thực cho đánh giá sản phẩm trên các sàn (Tiki, Shopee), kết hợp hai hướng tiếp cận: mô hình nền tảng Spark ML (TF‑IDF + Logistic Regression) và mô hình ngôn ngữ hiện đại PhoBERT chạy trên GPU. Hệ thống được thiết kế theo kiến trúc microservices, truyền dữ liệu qua Kafka, lưu trữ ở MongoDB, và trực quan hóa qua UI Streamlit theo thời gian thực.

---

## Tóm tắt điều hành (Executive Summary)
- Thu thập đánh giá sản phẩm theo thời gian thực → xử lý song song bởi 2 mô hình → lưu và hiển thị trên dashboard.
- Chia tách dữ liệu 50/50 theo `hash(review_id) % 2` đảm bảo mỗi đánh giá chỉ được xử lý bởi một mô hình.
- Lưu trữ ở MongoDB (collections: `reviews_raw`, `reviews_pred`), hiển thị trên Streamlit với auto-refresh 3 giây.
- Khắc phục các sự cố vận hành đã gặp: trùng lặp khóa Mongo (E11000), lỗi OOM Spark, lỗi Arrow serialization trên UI, không đồng nhất timestamp, thứ tự realtime.
- Kết quả: Hệ thống vận hành ổn định; đã ghi nhận hàng nghìn dự đoán thời gian thực từ cả hai mô hình trong quá trình kiểm thử nội bộ.

---

## Mục tiêu và phạm vi
- Xây dựng pipeline realtime end-to-end cho phân tích cảm xúc review tiếng Việt.
- Tích hợp hai mô hình: baseline nhẹ (Spark ML) và deep learning (PhoBERT) để so sánh, dự phòng và mở rộng.
- Hiển thị trực quan, theo dõi hoạt động hệ thống và đánh giá chất lượng mô hình.
- Phạm vi: Nguồn dữ liệu Tiki (API) và/hoặc Shopee (crawler HTML), xử lý thời gian thực, lưu trữ và trực quan hóa.

---

## Kiến trúc tổng thể

Tham chiếu: `README.md`, `PIPELINE.md`.

Sơ đồ luồng dữ liệu:
```
┌─────────────────────────────────────────────────────────────────┐
│                         UI (Streamlit)                          │
│  - Crawl Control  - Live Reviews  - Live Predictions            │
│  - Console Logs   - Evaluation   - Auto-refresh (3s)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       API (FastAPI)                             │
│  - Crawler endpoints (Tiki API only)                            │
│  - Data Splitting Logic: hash(review_id) % 2                    │
└─────────────────────────────────────────────────────────────────┘
            ↓                              ↓
    ┌──────────────────┐          ┌───────────────────┐
    │ Kafka: reviews   │          │ Kafka: reviews_raw│
    │   (hash = 1)     │          │    (hash = 0)     │
    └──────────────────┘          └───────────────────┘
            ↓                               ↓
┌─────────────────────┐        ┌─────────────────────┐
│ PhoBERT Consumer    │        │  Spark Streaming    │
│ - Batch reviews     │        │  - TF-IDF + LR      │
│ - Call inference    │        │  - Weak labeling    │
│ - Save predictions  │        │  - Incremental fit  │  
└─────────────────────┘        └─────────────────────┘
            ↓                               |
                                            |
  ┌────────────────────────────────────┐    |
  │   PhoBERT Inference Service (CUDA) │    |
  │   - wonrax/phobert-base-vietnamese │    |
  │   - GPU-accelerated inference      |    |  
  └────────────────────────────────────┘    |
                        ↓                   ↓
              ┌────────────────────────────────────────────┐
              │         MongoDB (reviews_db)               │
              │  - reviews_raw (crawler output)            │
              │  - reviews_pred (model predictions)        │
              └────────────────────────────────────────────┘
```

- Kafka Topics:
  - `reviews_raw` (hash=0) → Spark job.
  - `reviews` (hash=1) → PhoBERT consumer.
- MongoDB (DB: `reviews_db`):
  - `reviews_raw`: dữ liệu thô từ crawler.
  - `reviews_pred`: kết quả dự đoán từ hai mô hình, có index/unique phù hợp.
- UI Streamlit: Tabs Live Reviews, Live Predictions, Console Logs, Evaluation.

---

## Thành phần hệ thống

### 1) Thu thập dữ liệu
- Tiki API (trong `api/`): hỗ trợ crawl theo brand/store/category, giới hạn reviews mỗi sản phẩm (tối đa 500), và số ngày lấy về.
- Shopee crawler HTML (tùy chọn, trong `crawler-html/`): Playwright + các kỹ thuật tránh bot; có thể publish thử dữ liệu vào Kafka khi cần kiểm thử.
- Kết quả lưu vào `reviews_raw` với các trường: platform, review_id, product_id, product_name, rating, title, content, category_id/name, reviewer_name, create_time, crawled_at, v.v.

### 2) Lớp điều phối/API (`api/`)
- FastAPI cung cấp endpoint điều khiển crawl, route model.
- Thực hiện logic chia tách dữ liệu: `hash(review_id) % 2` → gửi tới topic thích hợp.
```python
review_hash = hash(review_id) % 2
if review_hash == 0:
    producer.send('reviews_raw', value=review)  # → Spark
else:
    producer.send('reviews', value=review)       # → PhoBERT
```
### 3) Kafka + Zookeeper
- Kafka làm message broker; Zookeeper giữ vai trò điều phối broker/metadata (theo Docker Compose hiện tại).
- Topics: `reviews`, `reviews_raw`.

### 4) Spark Structured Streaming (`spark-job/`)
- Đọc từ Kafka topic `reviews_raw`.
- Làm sạch text, ghép `title + content` → TF‑IDF → Logistic Regression.
- Gán nhãn yếu từ rating (1–2: Không tốt, 4–5: Tốt; 3: trung tính, có thể bỏ).
- Huấn luyện cập nhật theo micro-batch khi đủ dữ liệu; dự đoán theo thời gian thực.
- Ghi `reviews_pred` với các trường: review_id, platform, product_id, category_id/name, rating, text, pred_label, pred_label_vn, pred_proba_vec, model="spark-baseline", ts.

### 5) PhoBERT Inference (`phobert-infer/`) + Consumer (`phobert-consumer/`)
- Dịch vụ REST `/predict` (GPU/CUDA) nhận batch texts và trả về `pred` + `proba`.
- Consumer lắng nghe Kafka topic `reviews`, gom batch (128 hoặc theo latency), gọi infer, ghi MongoDB với `model="phobert"`.
- Tối ưu throughput bằng batch lớn và GPU.

### 6) MongoDB (`mongo`)
- Chạy chế độ replica set `rs0` để tương thích connector Spark.
- Index và ràng buộc đặc thù:
  - `reviews_pred`: unique compound trên `(review_id, model)` để tránh trùng dự đoán cùng review.

### 7) UI (Streamlit) (`ui/app.py`)
- Live Reviews: xem dữ liệu thô mới nhất (paginate, truncate, sort theo `crawled_at`).
- Live Predictions: xem dự đoán từ cả hai mô hình, sắp xếp theo `_id` (ObjectId) để đảm bảo thứ tự realtime; chuẩn hóa timestamp.
- Console Logs: hoạt động gần đây của crawler & predictions.
- Evaluation: sinh mẫu ngẫu nhiên để đánh giá, biểu đồ theo sản phẩm, theo ngành hàng, top sản phẩm tiêu cực.
- Auto-refresh 3 giây.

---

## Luồng dữ liệu và logic chia tách

Logic routing (tại API):
```python
review_hash = hash(review_id) % 2
if review_hash == 0:
    producer.send('reviews_raw', value=review)  # → Spark
else:
    producer.send('reviews', value=review)      # → PhoBERT
```
Lợi ích:
- Không trùng lặp xử lý cùng một review giữa hai mô hình.
- Đảm bảo phân phối công bằng 50/50 để so sánh.
- Dễ điều chỉnh tỷ lệ nếu cần (ví dụ 70/30).

---

## Mô hình dữ liệu (MongoDB)

### `reviews_raw`
- Trường chính: `_id`, `platform`, `review_id`, `product_id`, `product_name`, `product_url`, `category_id`, `category_name`, `rating`, `title`, `content`, `reviewer_name`, `create_time`, `crawled_at`, `source_type`, `source_id`.
- Chỉ mục gợi ý: `{ platform:1, product_id:1, create_time:-1 }`.

### `reviews_pred`
- Trường chính: `_id`, `review_id`, `platform`, `product_id`, `category_id`, `category_name`, `rating`, `text`, `pred_label`, `pred_label_vn`, `pred_proba_vec`, `model` ("spark-baseline" | "phobert"), `ts` (datetime).
- Ràng buộc: Unique trên `(review_id, model)` để loại bỏ trùng lặp.

---

## Triển khai và vận hành

- Docker Compose orchestration: `mongo`, `zookeeper`, `kafka`, `api`, `spark-job`, `phobert-infer`, `phobert-consumer`, `ui`.
- Biến môi trường quan trọng (tham chiếu `README.md`):
  - `KAFKA_BOOTSTRAP`, `MONGO_URI` (dùng `?replicaSet=rs0`), `INFER_URL`, v.v.
- Yêu cầu GPU cho PhoBERT: NVIDIA driver + NVIDIA Container Toolkit.
- Checkpoint Spark: `/tmp/chk_sentiment` (cần reset khi muốn đọc lại dữ liệu cũ).

Cách chạy nhanh (PowerShell):
```powershell
docker-compose up -d --build
# Kiểm tra replicaset
docker exec mongo mongosh --eval "rs.status()"
# Mở UI: http://127.0.0.1:8501
```

---

## Sự cố điển hình và cách khắc phục (Lessons Learned)

1) Trùng khóa MongoDB (E11000) khi ghi `reviews_pred`:
- Nguyên nhân: cùng `review_id` và `model` bị ghi nhiều lần.
- Khắc phục: Thiết kế unique compound index và để DB bỏ qua bản trùng; Spark writer bọc try/catch; consumer dùng upsert best‑effort nếu cần.

2) Spark OutOfMemoryError (Java heap space):
- Nguyên nhân: tiền xử lý chống trùng lặp bằng cách đọc/collect IDs quá lớn.
- Khắc phục: bỏ dedup ở Spark, giao việc lọc trùng cho unique index MongoDB; giảm tải bộ nhớ và ổn định job.

3) UI Arrow serialization error (không convert datetime):
- Nguyên nhân: DataFrame chứa object datetime và non‑datetime lẫn lộn.
- Khắc phục: Convert toàn bộ cột kiểu object có giá trị datetime sang chuỗi ngay sau khi đọc từ MongoDB.

4) Thứ tự realtime không đúng khi sort theo `ts`:
- Nguyên nhân: `ts` từ hai mô hình khác kiểu (int vs datetime).
- Khắc phục: Chuẩn hóa `ts` thành datetime cho cả hai; đồng thời sort theo `_id` để đảm bảo đúng thứ tự chèn.

5) Kết nối nội bộ Docker:
- Sử dụng host nội bộ dịch vụ (ví dụ `mongo:27017`, `kafka:9092`) thay vì `localhost` trong container.

---

## Theo dõi và đánh giá

- UI cung cấp số liệu tổng quan: tổng reviews, tổng predictions, hoạt động gần đây.
- Evaluation tab hỗ trợ tạo mẫu ngẫu nhiên (100–5000) để phân tích theo sản phẩm, theo ngành hàng, và top tiêu cực.
- Nhãn tiếng Việt: 0=Không tốt, 1=Tốt, 2=Trung bình.
- Trong kiểm thử, hệ thống đã ghi nhận lượng dự đoán lớn từ cả hai pipeline; thời gian hiển thị realtime ổn định (auto-refresh 3 giây).

---

## Bảo mật và tuân thủ
- Tôn trọng điều khoản sử dụng của nền tảng (rate limit phù hợp, không lạm dụng crawler).
- Bảo vệ thông tin nhận dạng cá nhân (PII) nếu có, chỉ lưu trữ trường cần thiết.
- Không lộ khóa/bí mật; dùng biến môi trường và mạng nội bộ Docker.

---

## Hướng phát triển
- Chuyển Kafka sang KRaft (loại bỏ Zookeeper) khi phù hợp.
- Điều chỉnh tỉ lệ chia dữ liệu (ví dụ 70/30) theo tài nguyên mô hình.
- Bổ sung nguồn dữ liệu mới (Lazada, Sendo) và bộ chuẩn hóa text tốt hơn.
- Fine-tune PhoBERT theo domain cụ thể để tăng độ chính xác.
- Thêm cảnh báo realtime (alerting) khi tỷ lệ tiêu cực tăng bất thường.
- Tối ưu hiệu năng Spark (tuning executors, batch interval) khi scale lớn.

---

## Kết luận

Dự án đã xây dựng thành công một hệ thống phân tích cảm xúc tiếng Việt theo thời gian thực, kết hợp giữa tính nhẹ và tốc độ của Spark ML với độ chính xác cao của PhoBERT chạy GPU. Kiến trúc microservices giúp hệ thống linh hoạt, mở rộng, và dễ quan sát. Các sự cố quan trọng đã được xử lý, đảm bảo tính ổn định khi vận hành. Hệ thống sẵn sàng mở rộng theo nhu cầu nghiệp vụ và quy mô dữ liệu.

---

## Phụ lục A — Cách reset checkpoint Spark
```powershell
docker exec realtime-vn-sentiment-spark-job-1 rm -rf /tmp/chk_sentiment
docker restart realtime-vn-sentiment-spark-job-1
docker logs realtime-vn-sentiment-spark-job-1 --tail 50 | Select-String -Pattern "SPARK BATCH"
```

## Phụ lục B — Xóa dữ liệu thử nghiệm
```powershell
docker exec mongo mongosh reviews_db --quiet --eval "db.reviews_raw.deleteMany({}); db.reviews_pred.deleteMany({}); print('Data cleared successfully');"
```

## Phụ lục C — Xuất báo cáo ra Word (.docx)
- Cài đặt Pandoc (một lần):
  - Winget: `winget install --id JohnMacFarlane.Pandoc -e`
  - Hoặc Chocolatey: `choco install pandoc -y`
- Chuyển đổi Markdown → Word:
```powershell
pandoc -s docs/BAO_CAO_DU_AN.md -o docs/BAO_CAO_DU_AN.docx --metadata title="Báo cáo dự án"
```

(Ưu tiên giữ báo cáo ở Markdown để dễ chỉnh sửa; có thể xuất sang .docx khi nộp bài.)
