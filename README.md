# Realtime Vietnamese Product Sentiment — Flink + Kafka + MongoDB + PhoBERT

Hệ thống phân tích cảm xúc realtime cho review sản phẩm e-commerce (Tiki) sử dụng:
- **Apache Flink** - Stream processing với dual-model sentiment analysis
- **Kafka** - Message streaming cho realtime data pipeline
- **MongoDB Replica Set** - Distributed database storage
- **PhoBERT** - Transformer-based Vietnamese sentiment model
- **Streamlit** - Realtime dashboard với auto-refresh 3 giây

## Kiến trúc hệ thống

### Data Pipeline
```
Tiki Crawler → FastAPI → Kafka Topics (reviews/reviews_raw)
                              ↓                    ↓
                      Flink Job (Baseline)  Flink Job (PhoBERT)
                              ↓                    ↓
                         MongoDB (reviews_pred collection)
                                       ↓
                         Streamlit UI (realtime dashboard)
```

### Tính năng chính
- **Dual-model processing**: Hash-based data splitting
  - Hash-based routing: `hash(review_id) % 2`
  - `hash = 0` → `reviews_raw` topic → **Flink Baseline Model**
  - `hash = 1` → `reviews` topic → **Flink PhoBERT Model**
- **Content filtering**: Chỉ xử lý reviews có content > 3 ký tự
- **Realtime streaming**: Flink job chạy liên tục, xử lý từng message
- **Auto-scaling**: Flink TaskManager có thể scale theo workload

## Cài đặt nhanh

```powershell
# Clone repository
git clone https://github.com/benx3/realtime-vn-sentiment.git
cd realtime-vn-sentiment

# Khởi động toàn bộ hệ thống
docker-compose up -d --build

# Verify MongoDB replica set (tự động init)
docker exec mongo mongosh --eval "rs.status()"

# Kiểm tra Flink jobs
docker logs flink-job-submit --tail=50

# Mở UI tại http://localhost:8501
# Mở Flink Dashboard tại http://localhost:8081
```

## Tính năng

### Tiki API Crawler
- **Brand URLs**: `https://tiki.vn/thuong-hieu/nan.html`
- **Store URLs**: `https://tiki.vn/cua-hang/mrm-manlywear-official`
- **Category URLs**: `https://tiki.vn/thiet-bi-kts-phu-kien-so/c1815`
- Fetches real category names via API
- Extracts reviewer names từ `created_by` field
- Includes product URLs trong tất cả reviews
- Hỗ trợ lên tới 500 reviews mỗi product
- **Content filtering**: Chỉ xử lý reviews có content > 3 ký tự

### UI Dashboard (Streamlit)
- **Live Reviews** - Realtime view của crawled reviews với pagination
  - Platform, category, reviewer name, rating, content
  - Sorted by crawled time (newest first)
- **Live Predictions** - Predictions từ cả Baseline và PhoBERT models
  - Hiển thị sentiment predictions với Vietnamese labels
  - Hiển thị model source (`flink-baseline` hoặc `phobert`)
  - Timestamp tracking cho real-time updates
  - Fields: reviewer_name, content, title, product_id
- **Console Logs** - System activity monitoring
  - Recent crawler activity
  - Prediction logs với review details
- **Evaluation** - Batch inference và analytics
  - Random sample generation (100-5000 reviews)
  - **Top 10 Products by Reviews** - Bar chart với sentiment breakdown
  - **By Category** - Distribution across product categories
  - **Top 10 Worst Products** - Products với most negative reviews
  - **Review Details** - Search và view reviews theo:
    - Product Name (dropdown selector)
    - Product ID (text search)
  - Summary metrics: Total reviews, sentiment percentages
  - Tabbed review display: Tốt / Trung bình / Không tốt
- **Auto-refresh**: Mỗi 3 giây

### Docker Services
- `mongo` - MongoDB 6 với replica set rs0 (tự động initialize)
- `mongo-init` - Initialization service cho replica set
- `zookeeper`, `kafka` - Message broker với 2 topics: `reviews`, `reviews_raw`
- `api` - FastAPI crawler control + hash-based data splitting
- `flink-jobmanager`, `flink-taskmanager` - Apache Flink 1.18.0 cluster
- `flink-job-submit` - Container chạy Flink sentiment jobs
- `phobert-infer` - PhoBERT inference microservice (CUDA-enabled)
- `ui` - Streamlit realtime dashboard

### MongoDB Collections
- **reviews_raw** - Raw crawled reviews với metadata
  - Fields: `_id`, `platform`, `review_id`, `product_id`, `product_name`, `product_url`
  - `category_id`, `category_name`, `rating`, `title`, `content`
  - `reviewer_name`, `create_time`, `crawled_at`, `source_type`, `source_id`
- **reviews_pred** - Model predictions với fields:
  - `review_id`, `platform`, `product_id`, `category_id`, `category_name`
  - `rating`, `reviewer_name`, `title`, `content`
  - `text` (title + content), `pred_label`, `pred_label_vn`
  - `pred_proba_vec` (probability distribution as JSON string)
  - `model` (`flink-baseline` hoặc `phobert`)
  - `ts` (timestamp)

### Kafka Topics
- **reviews** - Reviews cho PhoBERT model (hash=1)
- **reviews_raw** - Reviews cho Baseline model (hash=0)

## Cấu hình

### Environment Variables
- `KAFKA_BOOTSTRAP`: Kafka server (default: `realtime-vn-sentiment-kafka-1:9092`)
- `MONGO_URI`: MongoDB connection (default: `mongodb://mongo:27017/?replicaSet=rs0`)
- `INFER_URL`: PhoBERT inference endpoint (default: `http://phobert-infer:5000/predict`)
- `DEVICE`: GPU device (default: `cuda` cho PhoBERT)

## Lưu ý
- **GPU Required**: PhoBERT sử dụng CUDA. Đảm bảo:
  1. NVIDIA GPU + drivers đã cài đặt
  2. Docker với NVIDIA Container Toolkit
  3. `nvidia-smi` hoạt động trên host
- **Model**: Sử dụng `wonrax/phobert-base-vietnamese-sentiment` (download tự động lúc build)
- **Rate Limits**: Tuân thủ platform ToS, sử dụng crawl rates hợp lý
- **Data Split**: Hash-based routing đảm bảo không duplicate processing
  - Hash routing: 50% baseline model, 50% PhoBERT model
  - Content filtering: Chỉ xử lý reviews có content > 3 ký tự
  - Để sử dụng local fine-tuned model, mount vào `phobert-infer/models/phobert-sentiment-best/` và giữ `MODEL_DIR` là default
- Verify device: `curl http://localhost:9000/healthz` → `"device": "cuda"`

### Troubleshooting
- Nếu build fail do không internet, bỏ build-time download và đặt model folder vào `phobert-infer/models/phobert-sentiment-best/` manually, sau đó rebuild
- Nếu GPU không visible, check: `docker run --gpus all --rm nvidia/cuda:12.1.1-runtime-ubuntu22.04 nvidia-smi`
- MongoDB replica set không init: Check logs `docker logs mongo-init`
- Flink jobs không chạy: Check logs `docker logs flink-job-submit --tail=50`

## Docker Commands cho Maintenance

### Rebuild và Restart Services
```powershell
# Rebuild chỉ UI service với code changes mới nhất
docker-compose up -d --build ui

# Rebuild tất cả services
docker-compose up -d --build

# Rebuild service cụ thể without cache
docker-compose build --no-cache flink-job-submit
docker-compose up -d flink-job-submit

# Quick restart without rebuild
docker-compose restart ui
```

### Monitoring và Logs
```powershell
# View service logs real-time
docker logs ui -f
docker logs flink-job-submit --tail 50

# Check container status
docker ps

# Monitor Flink processing
docker logs flink-job-submit --tail 100 | Select-String -Pattern "Processing review"

# Check Flink Dashboard
# Mở http://localhost:8081 để xem job status
```

### Database Operations
```powershell
# Check review counts
docker exec mongo mongosh --eval "db.reviews_raw.countDocuments({})" reviews_db

# Clear test data
docker exec mongo mongosh reviews_db --quiet --eval "db.reviews_raw.deleteMany({}); db.reviews_pred.deleteMany({}); print('Data cleared successfully');"

# Verify deletion
docker exec mongo mongosh reviews_db --quiet --eval "print('reviews_raw count:', db.reviews_raw.countDocuments({})); print('reviews_pred count:', db.reviews_pred.countDocuments({}));"

# Check MongoDB replica set status
docker exec mongo mongosh --eval "rs.status()"
```

### Performance Optimization
```powershell
# Clean up unused Docker images
docker image prune -a -f

# Reset Kafka consumer groups (để process lại từ đầu)
docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --delete --group flink-baseline-group
docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --delete --group flink-phobert-group
docker restart flink-job-submit

# Restart data processing services
docker-compose restart spark-job phobert-consumer
```