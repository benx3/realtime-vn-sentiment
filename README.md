# Realtime Vietnamese Product Sentiment — Spark + Kafka + Mongo + PhoBERT + UI

This project streams e-commerce reviews (Shopee, Tiki) in **realtime**, performs **dual-model sentiment analysis** with data splitting:
- **Spark Baseline** (TF-IDF + Logistic Regression) - processes 50% of reviews
- **PhoBERT** (transformer-based) - processes the other 50% of reviews

Reviews are stored in **MongoDB**, predictions visualized in **Streamlit UI** with realtime auto-refresh every 3 seconds.

## Architecture Overview

### Data Flow
```
Tiki Crawler → API → Kafka Topics (reviews/reviews_raw)
                            ↓                    ↓
                    PhoBERT Consumer      Spark Streaming
                            ↓                    ↓
                        MongoDB (reviews_pred collection)
                                      ↓
                            Streamlit UI (realtime dashboard)
```

### Data Splitting Logic
- Hash-based routing: `hash(review_id) % 2`
  - `hash = 0` → `reviews_raw` topic → **Spark Baseline**
  - `hash = 1` → `reviews` topic → **PhoBERT**
- Ensures no duplicate predictions between models
- Each review processed by exactly ONE model

## Quick Start
```powershell
git clone https://github.com/benx3/realtime-vn-sentiment.git
cd realtime-vn-sentiment
docker-compose up -d --build

# Verify mongo replicaset (automatic on first run)
docker exec mongo mongosh --eval "rs.status()"

# Open UI at http://127.0.0.1:8501
```

## Features

### Tiki API Crawler
- **Brand URLs**: `https://tiki.vn/thuong-hieu/nan.html`
- **Store URLs**: `https://tiki.vn/cua-hang/mrm-manlywear-official`
- **Category URLs**: `https://tiki.vn/thiet-bi-kts-phu-kien-so/c1815`
- Fetches real category names via API
- Extracts reviewer names from `created_by` field
- Includes product URLs in all reviews
- Supports up to 500 reviews per product

### UI Dashboard (Streamlit)
- **Live Reviews** - Realtime view of crawled reviews with pagination
  - Platform, category, reviewer name, rating, content
  - Sorted by crawled time (newest first)
- **Live Predictions** - Predictions from both Spark and PhoBERT models
  - Shows sentiment predictions with Vietnamese labels
  - Displays model source (spark-baseline or phobert)
  - Timestamp tracking for real-time updates
- **Console Logs** - System activity monitoring
  - Recent crawler activity
  - Prediction logs with review details
- **Evaluation** - Batch inference and analytics
  - Random sample generation (100-5000 reviews)
  - **Top 10 Products by Reviews** - Horizontal bar chart with sentiment breakdown
  - **By Category** - Distribution across product categories
  - **Top 10 Worst Products** - Products with most negative reviews
  - **Review Details** - Search and view reviews by:
    - Product Name (dropdown selector)
    - Product ID (text search)
  - Summary metrics: Total reviews, sentiment percentages
  - Tabbed review display: Tốt / Trung bình / Không tốt
- **Auto-refresh**: Every 3 seconds

### Services
- `mongo` (MongoDB + replicaset for Spark connector)
- `zookeeper`, `kafka` (message broker with 2 topics: `reviews`, `reviews_raw`)
- `api` (FastAPI) — crawler control endpoints + data splitting logic
- `spark-job` — Spark Structured Streaming baseline model
- `phobert-infer` — PhoBERT inference microservice (CUDA-enabled)
- `phobert-consumer` — Kafka consumer for PhoBERT predictions
- `ui` — Streamlit realtime dashboard

### MongoDB Collections
- **reviews_raw** - Raw crawled reviews with metadata (platform, category_name, reviewer_name, product_url)
  - Fields: `_id`, `platform`, `review_id`, `product_id`, `product_name`, `product_url`
  - `category_id`, `category_name`, `rating`, `title`, `content`
  - `reviewer_name`, `create_time`, `crawled_at`, `source_type`, `source_id`
- **reviews_pred** - Model predictions with fields:
  - `review_id`, `platform`, `product_id`, `category_id`, `category_name`
  - `rating`, `text` (title + content)
  - `pred_label` (0=Không tốt, 1=Tốt, 2=Trung bình)
  - `pred_label_vn` (Vietnamese label)
  - `pred_proba_vec` (probability distribution as JSON string)
  - `model` (`spark-baseline` or `phobert`)
  - `ts` (timestamp)

### Kafka Topics
- **reviews** - Reviews for PhoBERT consumer (hash=1)
- **reviews_raw** - Reviews for Spark streaming (hash=0)

## Configuration

### Environment Variables
- `KAFKA_BOOTSTRAP`: Kafka server (default: `realtime-vn-sentiment-kafka-1:9092`)
- `MONGO_URI`: MongoDB connection (default: `mongodb://mongo:27017/?replicaSet=rs0`)
- `INFER_URL`: PhoBERT inference endpoint (default: `http://phobert-infer:5000/predict`)
- `DEVICE`: GPU device (default: `cuda` for PhoBERT)

## Notes
- **GPU Required**: PhoBERT uses CUDA. Ensure:
  1. NVIDIA GPU + drivers installed
  2. Docker with NVIDIA Container Toolkit
  3. `nvidia-smi` works on host
- **Model**: Uses `wonrax/phobert-base-vietnamese-sentiment` (downloaded at build time)
- **Rate Limits**: Respect platform ToS, use reasonable crawl rates
- **Data Split**: 50/50 between models ensures no duplicate processing
  - To use a local fine-tuned model, mount it to `phobert-infer/models/phobert-sentiment-best/` and keep `MODEL_DIR` as default.
- Verify device: `curl http://localhost:9000/healthz` → should return `"device": "cuda"`.

### Troubleshooting
- If build fails fetching model (no internet), remove the build-time download and place the model folder under `phobert-infer/models/phobert-sentiment-best/` manually, then rebuild.
- If GPU not visible, check: `docker run --gpus all --rm nvidia/cuda:12.1.1-runtime-ubuntu22.04 nvidia-smi`.

## Docker Commands for Maintenance

### Rebuild and Restart Services
```powershell
# Rebuild only UI service with latest code changes
docker-compose up -d --build ui

# Rebuild all services
docker-compose up -d --build

# Rebuild specific service without cache
docker-compose build --no-cache ui
docker-compose up -d ui

# Quick restart without rebuild
docker-compose restart ui
```

### Monitoring and Logs
```powershell
# View service logs in real-time
docker logs ui -f
docker logs realtime-vn-sentiment-spark-job-1 --tail 50

# Check container status
docker ps

# Monitor Spark processing
docker logs realtime-vn-sentiment-spark-job-1 --tail 50 | Select-String -Pattern "SPARK BATCH"
```

### Database Operations
```powershell
# Check review counts
docker exec mongo mongosh --eval "db.reviews_raw.countDocuments({})" reviews_db

# Clear test data
docker exec mongo mongosh reviews_db --quiet --eval "db.reviews_raw.deleteMany({}); db.reviews_pred.deleteMany({}); print('Data cleared successfully');"

# Verify deletion
docker exec mongo mongosh reviews_db --quiet --eval "print('reviews_raw count:', db.reviews_raw.countDocuments({})); print('reviews_pred count:', db.reviews_pred.countDocuments({}));"
```

### Performance Optimization
```powershell
# Clean up unused Docker images
docker image prune -a -f

# Reset Spark checkpoint (if not processing existing data)
docker exec realtime-vn-sentiment-spark-job-1 rm -rf /tmp/chk_sentiment
docker restart realtime-vn-sentiment-spark-job-1

# Restart data processing services
docker-compose restart spark-job phobert-consumer
```