# Realtime Vietnamese Product Sentiment — Spark + Kafka + Mongo + PhoBERT + UI

This project streams e-commerce reviews (Shopee, Tiki) in **realtime**, performs **dual-model sentiment analysis** with data splitting:
- **Spark Baseline** (TF-IDF + Logistic Regression) - processes 50% of reviews
- **PhoBERT** (transformer-based) - processes the other 50% of reviews

Reviews are stored in **MongoDB**, predictions visualized in **Streamlit UI** with realtime auto-refresh every 5 seconds.

## Architecture Overview

### Data Flow
```
Crawler (Shopee/Tiki) → API → Kafka Topics (reviews/reviews_raw)
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
```bash
git clone <this-repo>
cd realtime-vn-sentiment
docker compose up -d --build

# initialize mongo replicaset (automatic on first run)
docker exec -it mongo mongosh --eval "rs.status()"

# open UI at http://127.0.0.1:8501
```

## Features

### Crawlers
1. **Shopee HTML Crawler** (Playwright-based, no API required)
   - Shop URLs: `https://shopee.vn/olay_officialstorevn#product_list`
   - Features: pause/resume, proxy pool, rate limiting

2. **Tiki API Crawler** (official API with token)
   - **Brand URLs**: `https://tiki.vn/thuong-hieu/nan.html`
   - **Store URLs**: `https://tiki.vn/cua-hang/mrm-manlywear-official`
   - **Category URLs**: `https://tiki.vn/thiet-bi-kts-phu-kien-so/c1815`
   - Fetches real category names via API
   - Extracts reviewer names from `created_by` field
   - Includes product URLs in all reviews

### UI Dashboard (Streamlit)
- **Live Reviews** - Realtime view of crawled reviews with category names, reviewer names, product URLs
- **Live Predictions** - Predictions from both Spark and PhoBERT models
- **Console Logs** - Prediction activity log
- **Evaluation** - Batch inference testing
- **Auto-refresh**: Every 5 seconds

### Services
- `mongo` (MongoDB + replicaset for Spark connector)
- `zookeeper`, `kafka` (message broker with 2 topics: `reviews`, `reviews_raw`)
- `api` (FastAPI) — crawler control endpoints + data splitting logic
- `crawler-html` (Playwright) — Shopee HTML crawler
- `spark-job` — Spark Structured Streaming baseline model
- `phobert-infer` — PhoBERT inference microservice (CUDA-enabled)
- `phobert-consumer` — Kafka consumer for PhoBERT predictions
- `ui` — Streamlit realtime dashboard

### MongoDB Collections
- **reviews_raw** - Raw crawled reviews with metadata (platform, category_name, reviewer_name, product_url)
- **reviews_pred** - Model predictions with fields:
  - `platform`, `product_id`, `category_id`, `category_name`
  - `pred_label` (0=Không tốt, 1=Tốt, 2=Trung bình)
  - `pred_label_vn` (Vietnamese label)
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

-xóa data test
docker exec mongo mongosh reviews_db --quiet --eval "db.reviews_raw.deleteMany({}); db.reviews_pred.deleteMany({}); print('Data cleared successfully');"
-kiem tra lại đã xóa hết chưa 
docker exec mongo mongosh reviews_db --quiet --eval "print('reviews_raw count:', db.reviews_raw.countDocuments({})); print('reviews_pred count:', db.reviews_pred.countDocuments({}));"

- restart lại service để chạy từ lúc này.
docker-compose restart spark-job phobert-consumer