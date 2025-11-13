# System Pipeline & Architecture

## High-level Flow
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
│ Flink PhoBERT Job   │        │  Flink Baseline Job │
│ - Kafka consumer    │        │  - TF-IDF + LR      │
│ - Content filter    │        │  - Content filter   │
│ - Call inference    │        │  - Weak labeling    │
│ - Save predictions  │        │  - Incremental fit  │  
└─────────────────────┘        └─────────────────────┘
            ↓                                   
  ┌────────────────────────────────────┐        
  │   PhoBERT Inference Service (CUDA) │        
  │   - wonrax/phobert-base-vietnamese │        
  │   - GPU-accelerated inference      │        
  └────────────────────────────────────┘        
                        ↓                       
              ┌────────────────────────────────────────────┐
              │         MongoDB (reviews_db)               │
              │  - reviews_raw (crawler output)            │
              │  - reviews_pred (model predictions)        │
              │    + reviewer_name, content, title         │
              └────────────────────────────────────────────┘
```

## Components

### 1. Tiki API Crawler

#### Technology & Features
- **Technology**: Direct API calls với X-Guest-Token
- **Endpoints**:
  - Products by category: `/api/v2/products?category={id}`
  - Products by brand: `/api/v2/products?q={brand}`
  - Products by store: `/api/v2/products?seller_id={id}`
  - Reviews: `/api/v2/reviews?product_id={id}`
  - Category info: `/api/v2/categories/{id}`
- **Features**:
  - Real category names từ API
  - Reviewer names từ `created_by` field
  - Product URLs: `https://tiki.vn/product-p{id}.html`
  - Pagination support (20 reviews per page, up to 500 per product)
  - Start/Stop controls từ UI
- **Output**: `reviews_raw` collection với enhanced metadata

### 2. Data Splitting (API Layer)
```python
review_hash = hash(review_id) % 2
if review_hash == 0:
    producer.send('reviews_raw', value=review)  # → Flink Baseline
else:
    producer.send('reviews', value=review)       # → Flink PhoBERT
```
- **Purpose**: Prevent duplicate predictions
- **Ratio**: 50/50 split giữa models
- **Guarantee**: Mỗi review processed bởi chính xác ONE model

### 3. Content Filtering
```python
# Trong cả 2 Flink jobs (baseline và phobert)
content = review.get('content', '')
if len(content) <= 3:
    skip_count += 1
    if skip_count % 50 == 0:
        print(f"Skipped {skip_count} reviews with content <= 3 chars")
    continue  # Bỏ qua review ngắn
```
- **Purpose**: Đảm bảo data quality cho AI training
- **Threshold**: Content > 3 ký tự
- **Impact**: Lọc bỏ reviews rỗng hoặc quá ngắn

### 4. Model Pipeline

#### Flink Baseline Job (flink-job/simple_sentiment_job.py)
- **Input**: Kafka topic `reviews_raw` (hash=0 reviews)
- **Technology**: Python Kafka Consumer + Scikit-learn
- **Processing**:
  1. Content filtering (len(content) > 3)
  2. Text cleaning (Tokenizer → StopWordsRemover)
  3. Weak labeling từ star ratings
  4. TF-IDF vectorization
  5. Logistic Regression (incremental fit per batch)
- **Output**: `reviews_pred` với `model="flink-baseline"`
- **Schema**: Includes `review_id`, `reviewer_name`, `content`, `title`, `category_name`, `pred_proba_vec`
- **Features**: 
  - Realtime streaming với auto_offset_reset='earliest'
  - Content quality filtering (>3 chars)
  - Detailed logging for processing
  - Vietnamese label mapping (Tốt/Trung bình/Không tốt)

#### Flink PhoBERT Job (flink-job/simple_sentiment_job.py)
- **Input**: Kafka topic `reviews` (hash=1 reviews)
- **Technology**: Python Kafka Consumer + HTTP requests
- **Processing**:
  1. Content filtering (len(content) > 3)
  2. Call PhoBERT inference service
  3. Process predictions với Vietnamese labels
  4. Save to MongoDB
- **Output**: `reviews_pred` với `model="phobert"`
- **Schema**: Same fields as baseline + PhoBERT probabilities
  
- **PhoBERT Inference Service** (`phobert-infer`):
  - Model: `wonrax/phobert-base-vietnamese-sentiment`
  - CUDA-accelerated (GPU required)
  - REST API: `POST /predict` với `{"texts": [...]}`
  - Returns: `{"pred": [...], "proba": [...]}`

### 5. Database Schema

#### reviews_raw Collection
```javascript
{
  _id: "tiki_20185286_1762507996426",
  platform: "tiki",              // "shopee" hoặc "tiki"
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
  review_id: "20185286",         // Added cho exact queries
  platform: "tiki",
  product_id: "278069931",
  category_id: "8594",
  category_name: "Ô Tô - Xe Máy - Xe Đạp",
  rating: 5,
  reviewer_name: "Nguyen Van A",  // Từ created_by field
  title: "Sản phẩm tuyệt vời",    // Review title
  content: "Cực kì hài lòng...",  // Review content
  text: "Sản phẩm tuyệt vời Cực kì hài lòng...",  // title + content
  pred_label: 1,                 // 0=Không tốt, 1=Tốt, 2=Trung bình
  pred_label_vn: "Tốt",
  pred_proba_vec: "[0.05, 0.92, 0.03]",
  model: "phobert",              // "flink-baseline" hoặc "phobert"
  ts: 1762508010
}
```

### 6. UI Dashboard (Streamlit)

#### Live Reviews Tab
- Displays: platform, category_name, reviewer_name, product_name, rating, content
- Sorted by: `crawled_at` (descending)
- Pagination: 20 rows per page
- Auto-refresh: 3 giây

#### Live Predictions Tab
- Displays: platform, category_name, reviewer_name, product_id, pred_label_vn, content, model
- Shows predictions từ CẢ HAI models (flink-baseline và phobert)
- Sorted by: `_id` (ObjectId, descending) cho reliable newest-first ordering
- Timestamp column (`ts_human`) for tracking
- "Last refresh" indicator showing update time
- Auto-refresh: 3 seconds

#### Console Logs Tab
- **Recent Crawler Activity**: Last 20 crawled reviews
- **Recent Predictions**: Last 20 predictions with details
- Shows: Timestamp, Review ID, Category, Product, Prediction, Model
- Helps monitor system activity in real-time
- Auto-refresh: 3 seconds

#### Evaluation Tab
- **Manual Evaluation**: Batch inference testing
  - Sample size: 100-5000 reviews (adjustable)
  - Random sampling from `reviews_raw` collection
  - Persistent results across auto-refreshes
- **Top 10 Products by Reviews**: Horizontal bar chart
  - Shows review count distribution
  - Color-coded by sentiment (Tốt/Trung bình/Không tốt)
  - Sorted by total review count
- **By Category**: Vertical bar chart
  - Sentiment distribution across product categories
  - Color mapping: Green (#2ecc71), Yellow (#f39c12), Red (#e74c3c)
- **Top 10 Worst Products**: Horizontal bar chart
  - Products with most "Không tốt" reviews
  - Gradient red color scale for visual impact
- **Review Details**: Interactive product review viewer
  - **Search modes**:
    - Product Name: Dropdown selector with full product names
    - Product ID: Text search (exact or partial match)
  - **Summary metrics**: Total reviews, sentiment percentages (4 columns)
  - **Tabbed reviews**: ✅ Tốt, ⚠️ Trung bình, ❌ Không tốt
  - **Expandable details**: Rating, reviewer name, title, content, metadata
  - Uses `review_id` for exact MongoDB queries (no regex errors)

## Data Model

### Collections
- **reviews_raw**: Raw crawled reviews với full metadata
- **reviews_pred**: Model predictions từ cả Flink Baseline và PhoBERT
  - Includes: reviewer_name, content, title, product_id
  - Content filtering: Only reviews với content > 3 chars

### Kafka Topics
- **reviews**: Flink PhoBERT job input (hash=1)
- **reviews_raw**: Flink Baseline job input (hash=0)

## Running Step-by-Step

1. **Start services**:
   ```powershell
   docker-compose up -d --build
   ```

2. **Verify MongoDB replica set** (tự động init):
   ```powershell
   docker exec mongo mongosh --eval "rs.status()"
   ```

3. **Check service status**:
   ```powershell
   docker ps
   docker logs flink-job-submit --tail 50
   docker logs phobert-infer --tail 20
   ```

4. **Check Flink processing**:
   ```powershell
   docker logs flink-job-submit --tail 100 | Select-String -Pattern "Processing review"
   ```

5. **Access UI** tại `http://localhost:8501`

6. **Access Flink Dashboard** tại `http://localhost:8081`

5. **Start crawling**:
   - **Tiki**: Choose crawl type (brand/store/category) → Enter URL → Start
   - Configure: Max products, reviews per product (up to 500), days back

6. **Monitor**:
   - Live Reviews: See incoming reviews with realtime updates
   - Live Predictions: Xem predictions từ cả Flink Baseline và PhoBERT
   - Console Logs: Track crawler và prediction activity
   - Evaluation: Generate samples và view analytics charts

## Key Features

### Data Splitting Benefits
- **No Duplicates**: Mỗi review processed một lần
- **Fair Comparison**: 50/50 split đảm bảo balanced evaluation
- **Resource Optimization**: Cả hai models chạy song song
- **Scalability**: Có thể adjust split ratio bằng modify hash logic

### Content Filtering
- **Quality Control**: Chỉ xử lý reviews có content > 3 ký tự
- **Training Data Quality**: Đảm bảo đủ dữ liệu cho AI training
- **Skip Tracking**: Log mỗi 50 reviews bị skip

### Realtime Processing
- **UI Auto-refresh**: 3-giây intervals
- **Kafka Streaming**: Sub-second message delivery
- **Flink Processing**: Continuous stream processing
- **PhoBERT Batching**: Optimized cho GPU throughput

## Troubleshooting

### Flink Jobs Không Process Existing Data
Nếu Kafka consumer không đọc existing messages:
```powershell
# Reset consumer groups
docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --delete --group flink-baseline-group
docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --delete --group flink-phobert-group

# Restart Flink jobs
docker restart flink-job-submit

# Verify processing trong logs
docker logs flink-job-submit --tail 100 | Select-String -Pattern "Processing review"
```

### No Predictions Appearing
1. Check consumer offsets:
   ```powershell
   docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group flink-baseline-group
   docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group flink-phobert-group
   ```

2. Check Flink logs:
   ```powershell
   docker logs flink-job-submit --tail 50
   ```

3. Verify data splitting:
   ```powershell
   docker logs api --tail 30 | Select-String -Pattern "SPARK|PHOBERT"
   ```

### Duplicate Predictions
Reset consumer offsets:
```powershell
# Stop Flink jobs
docker-compose stop flink-job-submit

# Reset offsets
docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --delete --group flink-baseline-group
docker exec kafka kafka-consumer-groups --bootstrap-server localhost:9092 --delete --group flink-phobert-group

# Restart services
docker-compose start flink-job-submit
```

### Missing category_name hoặc reviewer_name
- Đảm bảo schema includes các fields:
  - Flink job: Check `create_prediction_doc()` trong `simple_sentiment_job.py`
  - Tiki crawler: Verify category API fetch và `created_by` extraction

### Review Details Display Issues
- **MongoDB regex errors**: Fixed bằng sử dụng `review_id` cho exact queries
- **Product không show reviews**: Đảm bảo dataframe có `review_id`, `product_id`, `product_name_full`
- **Search không work**: Check if Product ID search mode được selected correctly

### MongoDB Replica Set Không Initialize
```powershell
# Check mongo-init logs
docker logs mongo-init

# Manually initialize nếu cần
docker exec mongo mongosh --eval "rs.initiate({_id: 'rs0', members: [{_id: 0, host: 'mongo:27017'}]})"
```

## Extending the System

### Add New Data Sources
1. Implement crawler trong `api/crawlers/`
2. Follow `TikiClient` pattern
3. Đảm bảo output includes tất cả required fields
4. Add endpoint trong `api/main.py`

### Adjust Model Split
Modify trong `api/main.py`:
```python
# Change từ 50/50 sang 70/30 (Baseline/PhoBERT)
review_hash = hash(review_id) % 10
if review_hash < 7:  # 70% to Baseline
    producer.send('reviews_raw', value=review)
else:  # 30% to PhoBERT
    producer.send('reviews', value=review)
```

### Adjust Content Filtering Threshold
Modify trong `flink-job/simple_sentiment_job.py`:
```python
# Change từ >3 sang >10 chars
if len(content) <= 10:
    skip_count += 1
    continue
```

### Add More Models
1. Create new Kafka topic
2. Implement new consumer service
3. Update data splitting logic
4. Add model identifier to predictions
