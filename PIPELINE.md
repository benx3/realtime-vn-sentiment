# System Pipeline & Architecture

## High-level Flow
```
┌─────────────────────────────────────────────────────────────────┐
│                         UI (Streamlit)                          │
│  - Crawl Control  - Live Reviews  - Live Predictions           │
│  - Console Logs   - Evaluation   - Auto-refresh (5s)           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       API (FastAPI)                             │
│  - Crawler endpoints (Shopee HTML, Tiki API)                   │
│  - Data Splitting Logic: hash(review_id) % 2                   │
└─────────────────────────────────────────────────────────────────┘
                ↓                              ↓
    ┌──────────────────┐          ┌──────────────────┐
    │ Kafka: reviews   │          │ Kafka: reviews_raw│
    │   (hash = 1)     │          │    (hash = 0)     │
    └──────────────────┘          └──────────────────┘
            ↓                              ↓
┌─────────────────────┐        ┌─────────────────────┐
│ PhoBERT Consumer    │        │  Spark Streaming    │
│ - Batch reviews     │        │  - TF-IDF + LR      │
│ - Call inference    │        │  - Weak labeling    │
│ - Save predictions  │        │  - Incremental fit  │
└─────────────────────┘        └─────────────────────┘
            ↓                              ↓
    ┌────────────────────────────────────────────┐
    │   PhoBERT Inference Service (CUDA)        │
    │   - wonrax/phobert-base-vietnamese        │
    │   - GPU-accelerated inference             │
    └────────────────────────────────────────────┘
                        ↓
    ┌────────────────────────────────────────────┐
    │         MongoDB (reviews_db)               │
    │  - reviews_raw (crawler output)            │
    │  - reviews_pred (model predictions)        │
    └────────────────────────────────────────────┘
```

## Components

### 1. Crawlers

#### Shopee HTML Crawler (Playwright)
- **Technology**: Headless Chromium with Playwright
- **Method**: DOM scraping + JSON interception
- **Features**:
  - Pause/Resume/Stop controls
  - Proxy pool support
  - Rate limiting
  - Retry with backoff
  - Logs to MongoDB
- **Output**: `reviews_raw` collection

#### Tiki API Crawler
- **Technology**: Direct API calls with X-Guest-Token
- **Endpoints**:
  - Products by category: `/api/v2/products?category={id}`
  - Products by brand: `/api/v2/products?q={brand}`
  - Products by store: `/api/v2/products?seller_id={id}`
  - Reviews: `/api/v2/reviews?product_id={id}`
  - Category info: `/api/v2/categories/{id}`
- **Features**:
  - Real category names from API
  - Reviewer names from `created_by` field
  - Product URLs: `https://tiki.vn/product-p{id}.html`
  - Pagination support (20 reviews per page)
- **Output**: `reviews_raw` collection with enhanced metadata

### 2. Data Splitting (API Layer)
```python
review_hash = hash(review_id) % 2
if review_hash == 0:
    producer.send('reviews_raw', value=review)  # → Spark
else:
    producer.send('reviews', value=review)       # → PhoBERT
```
- **Purpose**: Prevent duplicate predictions
- **Ratio**: 50/50 split between models
- **Guarantee**: Each review processed by exactly ONE model

### 3. Model Pipeline

#### Spark Baseline (spark-job)
- **Input**: Kafka topic `reviews_raw` (hash=0 reviews)
- **Processing**:
  1. Text cleaning (Tokenizer → StopWordsRemover)
  2. Weak labeling from star ratings
  3. TF-IDF vectorization
  4. Logistic Regression (incremental fit per micro-batch)
- **Output**: `reviews_pred` with `model="spark-baseline"`
- **Schema**: Includes `category_name` field
- **Features**: Real-time streaming with checkpointing

#### PhoBERT Pipeline
- **PhoBERT Consumer** (`phobert-consumer`):
  - Consumes from Kafka topic `reviews` (hash=1 reviews)
  - Batches reviews (batch_size=128, max_latency=1500ms)
  - Calls PhoBERT inference service
  - Saves predictions to `reviews_pred` with `model="phobert"`
  
- **PhoBERT Inference Service** (`phobert-infer`):
  - Model: `wonrax/phobert-base-vietnamese-sentiment`
  - CUDA-accelerated (GPU required)
  - REST API: `POST /predict` with `{"texts": [...]}`
  - Returns: `{"pred": [...], "proba": [...]}`

### 4. Database Schema

#### reviews_raw Collection
```javascript
{
  _id: "tiki_20185286_1762507996426",
  platform: "tiki",              // "shopee" or "tiki"
  review_id: "20185286",
  product_id: "278069931",
  product_name: "Bút tẩy xóa vết trầy...",
  product_url: "https://tiki.vn/product-p278069931.html",
  category_id: "8594",
  category_name: "Ô Tô - Xe Máy - Xe Đạp",
  rating: 5,
  title: "Cực kì hài lòng",
  content: "Sản phẩm tốt...",
  reviewer_name: "Vân Thư",
  create_time: "1753674740",
  crawled_at: 1762508003.16,
  source_type: "category",       // "brand", "store", or "category"
  source_id: "8594"
}
```

#### reviews_pred Collection
```javascript
{
  _id: ObjectId("..."),
  platform: "tiki",
  product_id: "278069931",
  category_id: "8594",
  category_name: "Ô Tô - Xe Máy - Xe Đạp",
  rating: 5,
  text: "Cực kì hài lòng Sản phẩm tốt...",
  pred_label: 1,                 // 0=Không tốt, 1=Tốt, 2=Trung bình
  pred_label_vn: "Tốt",
  pred_proba_vec: "[0.05, 0.92, 0.03]",
  model: "phobert",              // "spark-baseline" or "phobert"
  ts: 1762508010
}
```

### 5. UI Dashboard (Streamlit)

#### Live Reviews Tab
- Displays: platform, category_name, reviewer_name, product_name, rating, content
- Sorted by: `crawled_at` (descending)
- Pagination: 20 rows per page
- Auto-refresh: 5 seconds

#### Live Predictions Tab
- Displays: platform, category_name, reviewer_name, product_id, pred_label_vn, content, model
- Shows predictions from BOTH models
- Timestamp column for tracking
- Auto-refresh: 5 seconds

#### Console Logs Tab
- Prediction activity log
- Shows: Timestamp, Review ID, Category, Product, Prediction, Model
- Helps monitor model activity

#### Evaluation Tab
- Batch inference testing
- Distribution charts by product and category
- Sample data view

## Data Model

### Collections
- **reviews_raw**: Raw crawled reviews with full metadata
- **reviews_pred**: Model predictions from both Spark and PhoBERT
- **control_configs**: Model routing configuration (currently unused with data splitting)

### Kafka Topics
- **reviews**: PhoBERT consumer input (hash=1)
- **reviews_raw**: Spark streaming input (hash=0)

## Running Step-by-Step

1. **Start services**:
   ```bash
   docker compose up -d --build
   ```

2. **Verify MongoDB replicaset**:
   ```bash
   docker exec -it mongo mongosh --eval "rs.status()"
   ```

3. **Check service status**:
   ```bash
   docker ps
   docker logs phobert-consumer --tail 20
   docker logs realtime-vn-sentiment-spark-job-1 --tail 20
   ```

4. **Access UI** at `http://127.0.0.1:8501`

5. **Start crawling**:
   - **Shopee**: Paste shop URL → Click "Start HTML Crawl"
   - **Tiki**: Choose crawl type (brand/store/category) → Enter URL → Start

6. **Monitor**:
   - Live Reviews: See incoming reviews with realtime updates
   - Live Predictions: See both Spark and PhoBERT predictions
   - Console Logs: Track model activity

## Key Features

### Data Splitting Benefits
- **No Duplicates**: Each review processed once
- **Fair Comparison**: 50/50 split ensures balanced evaluation
- **Resource Optimization**: Both models run in parallel
- **Scalability**: Can adjust split ratio by modifying hash logic

### Realtime Processing
- **UI Auto-refresh**: 5-second intervals
- **Kafka Streaming**: Sub-second message delivery
- **Spark Micro-batching**: Configurable batch intervals
- **PhoBERT Batching**: Optimized for GPU throughput

## Troubleshooting

### No Predictions Appearing
1. Check consumer offsets:
   ```bash
   docker exec realtime-vn-sentiment-kafka-1 kafka-consumer-groups \
     --bootstrap-server localhost:9092 --describe --group phobert-consumer-group
   ```

2. Check Spark logs:
   ```bash
   docker logs realtime-vn-sentiment-spark-job-1 --tail 50
   ```

3. Verify data splitting:
   ```bash
   docker logs api --tail 30 | grep "SPARK\|PHOBERT"
   ```

### Duplicate Predictions
- Reset consumer offsets:
  ```bash
  docker-compose stop phobert-consumer spark-job
  docker exec realtime-vn-sentiment-kafka-1 kafka-consumer-groups \
    --bootstrap-server localhost:9092 --group phobert-consumer-group \
    --reset-offsets --to-latest --topic reviews --execute
  ```

### Missing category_name
- Ensure schema includes `category_name`:
  - Spark: Check `StructType` definition
  - PhoBERT consumer: Check buffer append logic
  - Tiki crawler: Verify API fetch

## Extending the System

### Add New Data Sources
1. Implement crawler in `api/crawlers/`
2. Follow `TikiClient` pattern
3. Ensure output includes all required fields
4. Add endpoint in `api/main.py`

### Adjust Model Split
Modify in `api/main.py`:
```python
# Change from 50/50 to 70/30 (Spark/PhoBERT)
review_hash = hash(review_id) % 10
if review_hash < 7:  # 70% to Spark
    producer.send('reviews_raw', value=review)
else:  # 30% to PhoBERT
    producer.send('reviews', value=review)
```

### Add More Models
1. Create new Kafka topic
2. Implement new consumer service
3. Update data splitting logic
4. Add model identifier to predictions
