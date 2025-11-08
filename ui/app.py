import streamlit as st, pandas as pd, time, requests, os
from pymongo import MongoClient
import plotly.express as px
import math

API_BASE = os.getenv("API_BASE","http://api:8000")
MONGO_URI = os.getenv("MONGO_URI","mongodb://mongo:27017")
INFER_URL = os.getenv("INFER_URL","http://phobert-infer:5000")

st.set_page_config(page_title="VN Sentiment Realtime", layout="wide")
st.title("📊 VN Product Sentiment — Realtime Control")

# Auto-refresh configuration
REFRESH_INTERVAL = 3

# Initialize refresh counter
if 'refresh_counter' not in st.session_state:
    st.session_state.refresh_counter = 0

# Session state for pagination
if 'reviews_page' not in st.session_state:
    st.session_state.reviews_page = 1
if 'pred_page' not in st.session_state:
    st.session_state.pred_page = 1
if 'reviews_per_page' not in st.session_state:
    st.session_state.reviews_per_page = 20
if 'pred_per_page' not in st.session_state:
    st.session_state.pred_per_page = 20

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info()  # Force connection
    db = client["reviews_db"]  # Use reviews_db to match Spark job
except Exception as e:
    st.error(f"Cannot connect to MongoDB: {e}")
    st.stop()

with st.sidebar:
    st.subheader("Tiki Crawler")
    st.write("Support URLs:")
    st.write("• Brand: `tiki.vn/thuong-hieu/brand-name.html`")
    st.write("• Store: `tiki.vn/cua-hang/store-name`") 
    st.write("• Category: `tiki.vn/category-name/c1234`")
    
    tiki_urls = st.text_area("Tiki URLs (one per line)", 
                             "https://tiki.vn/do-choi-me-be/c2549")
    col1, col2 = st.columns(2)
    with col1:
        max_products_tiki = st.number_input("Max products", 10, 500, 50, 10, key="tiki_products")
        max_reviews_tiki = st.number_input("Reviews per product", 5, 500, 100, 5, key="tiki_reviews", help="Can now get up to 500 reviews per product")
    with col2:
        days_back_tiki = st.number_input("Days back", 1, 365, 30, 1, key="tiki_days")
    
    c_tiki = st.columns(3)
    if c_tiki[0].button("Start Tiki Crawl"):
        urls = [u.strip() for u in tiki_urls.splitlines() if u.strip()]
        if urls:
            payload = {
                "urls": urls,
                "max_products": int(max_products_tiki),
                "max_reviews_per_product": int(max_reviews_tiki),
                "days_back": int(days_back_tiki)
            }
            try:
                r = requests.post(f"{API_BASE}/crawl/tiki/start", json=payload)
                st.success(r.json())
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("Please enter at least one Tiki URL")
    
    if c_tiki[1].button("Stop Tiki"):
        r = requests.post(f"{API_BASE}/crawl/tiki/stop")
        st.warning(r.json())
    
    if c_tiki[2].button("Tiki Status"):
        try:
            r = requests.get(f"{API_BASE}/crawl/tiki/status")
            st.json(r.json())
        except Exception as e:
            st.error(f"Error: {e}")

    st.subheader("Model routing")
    active_model = st.selectbox("Active model", ["spark-baseline","phobert","both"], index=2)
    if st.button("Apply Global Routing"):
        requests.post(f"{API_BASE}/control/model", json={"active_model":active_model})
        st.success({"ok": True, "active_model": active_model})
    
    st.divider()
    st.subheader("🗑️ Data Management")
    
    # Auto-refresh toggle
    auto_refresh = st.checkbox("⏱️ Auto-refresh (3s)", value=True, help="Automatically refresh dashboard every 3 seconds")
    
    st.warning("⚠️ Danger Zone: This will permanently delete data!")
    col_clean1, col_clean2 = st.columns(2)
    with col_clean1:
        if st.button("🧹 Clear Reviews", type="secondary", use_container_width=True):
            result = db.reviews_raw.delete_many({})
            st.success(f"✅ Deleted {result.deleted_count:,} reviews")
            time.sleep(1)
            st.rerun()
    with col_clean2:
        if st.button("🧹 Clear Predictions", type="secondary", use_container_width=True):
            result = db.reviews_pred.delete_many({})
            st.success(f"✅ Deleted {result.deleted_count:,} predictions")
            time.sleep(1)
            st.rerun()
    if st.button("🗑️ Clear All Data", type="primary", use_container_width=True):
        raw_result = db.reviews_raw.delete_many({})
        pred_result = db.reviews_pred.delete_many({})
        st.success(f"✅ Deleted {raw_result.deleted_count:,} reviews + {pred_result.deleted_count:,} predictions")
        time.sleep(1)
        st.rerun()

live_tab, pred_tab, console_tab, eval_tab = st.tabs(["🟢 Live Reviews", "🔮 Live Predictions", "🖥️ Console Logs", "📈 Evaluation"]) 

with live_tab:
    # Controls for reviews
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        reviews_per_page = st.selectbox("Rows per page", [10, 20, 50, 100], 
                                        index=[10, 20, 50, 100].index(st.session_state.reviews_per_page),
                                        key="reviews_rows_select")
        st.session_state.reviews_per_page = reviews_per_page
    with col2:
        reviews_page_input = st.number_input("Page", min_value=1, value=st.session_state.reviews_page, 
                                            step=1, key="reviews_page_input")
        if reviews_page_input != st.session_state.reviews_page:
            st.session_state.reviews_page = reviews_page_input
            st.rerun()
    with col3:
        pass  # Column not used for now
        
    # Live Reviews Data Processing
    total_reviews = db.reviews_raw.count_documents({})
    skip_reviews = (st.session_state.reviews_page - 1) * st.session_state.reviews_per_page
    raw = list(db.reviews_raw.find()
              .sort([("crawled_at", -1)])  # Newest first by crawl time
              .skip(skip_reviews)
              .limit(st.session_state.reviews_per_page))
    
    # Process and display reviews data
    if raw:
        df_raw = pd.DataFrame(raw)
        if "platform" in df_raw.columns:
            display_cols = ["platform", "category_name", "reviewer_name", "product_name", "rating", "content", "create_time"]
            available_cols = [col for col in display_cols if col in df_raw.columns]
            
            # Select columns first to maintain order from MongoDB
            df_raw = df_raw[available_cols].fillna("")
            
            # Reset index to ensure proper display order
            df_raw = df_raw.reset_index(drop=True)
            
            # Truncate long product names for better display
            if "product_name" in df_raw.columns:
                df_raw['product_name'] = df_raw['product_name'].apply(
                    lambda x: (str(x)[:40] + "...") if pd.notna(x) and len(str(x)) > 40 else str(x)
                )
            
            # Truncate long content for better display
            if "content" in df_raw.columns:
                df_raw['content'] = df_raw['content'].apply(
                    lambda x: (str(x)[:80] + "...") if pd.notna(x) and len(str(x)) > 80 else str(x)
                )
        
        # Display reviews info and table
        total_pages_reviews = max(1, math.ceil(total_reviews / st.session_state.reviews_per_page))
        st.info(f"📊 Showing {len(df_raw)} reviews | Page {st.session_state.reviews_page}/{total_pages_reviews} | Total: {total_reviews:,}")
        st.dataframe(df_raw, use_container_width=True, height=400)
    else:
        st.warning("No reviews data available")

with pred_tab:
    # Controls for predictions
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        pred_per_page = st.selectbox("Rows per page", [10, 20, 50, 100], 
                                     index=[10, 20, 50, 100].index(st.session_state.pred_per_page),
                                     key="pred_rows_select")
        st.session_state.pred_per_page = pred_per_page
    with col2:
        pred_page_input = st.number_input("Page", min_value=1, value=st.session_state.pred_page, 
                                         step=1, key="pred_page_input")
        if pred_page_input != st.session_state.pred_page:
            st.session_state.pred_page = pred_page_input
            st.rerun()
    with col3:
        pass  # Column not used for now
        
    # Live Predictions Data Processing
    total_predictions = db.reviews_pred.count_documents({})
    skip_pred = (st.session_state.pred_page - 1) * st.session_state.pred_per_page
    # Use _id (ObjectId) for reliable descending insertion order across mixed ts types (int vs datetime)
    pred = list(db.reviews_pred.find()
               .sort([("_id", -1)])
               .skip(skip_pred)
               .limit(st.session_state.pred_per_page))
    
    # Process predictions data
    if pred:
        df_pred = pd.DataFrame(pred)
        
        # Check if text/content field exists in predictions
        content_col = None
        if "text" in df_pred.columns:
            content_col = "text"
        elif "content" in df_pred.columns:
            content_col = "content"
        
        # Truncate long text for display
        if content_col:
            df_pred['content_display'] = df_pred[content_col].apply(
                lambda x: (str(x)[:100] + "...") if pd.notna(x) and len(str(x)) > 100 else str(x)
            )
        else:
            df_pred['content_display'] = "N/A"
        
        # Get reviewer names by joining with reviews_raw
        if 'product_id' in df_pred.columns:
            product_ids = df_pred['product_id'].unique().tolist()
            reviewer_map = {}
            if product_ids:
                # Get recent reviews for these products to get reviewer names
                recent_reviews = list(db.reviews_raw.find(
                    {"product_id": {"$in": product_ids}},
                    {"product_id": 1, "reviewer_name": 1, "review_id": 1}
                ).sort([("crawled_at", -1)]).limit(200))
                
                for rev in recent_reviews:
                    pid = rev.get("product_id")
                    reviewer = rev.get("reviewer_name", "Anonymous")
                    review_id = str(rev.get("review_id", ""))
                    if pid and reviewer:
                        # Try to match by review_id first, then by product_id
                        reviewer_map[review_id] = reviewer
                        if pid not in reviewer_map:  # Only set if not already set
                            reviewer_map[pid] = reviewer
            
            # Map reviewer names to predictions
            df_pred['reviewer_name'] = df_pred.apply(
                lambda row: reviewer_map.get(str(row.get('review_id', '')), 
                           reviewer_map.get(row.get('product_id', ''), 'Anonymous')), 
                axis=1
            )
        else:
            df_pred['reviewer_name'] = 'Anonymous'
        
        # Check if pred_label_vn exists, otherwise fallback
        if "pred_label_vn" in df_pred.columns:
            display_cols = ["platform", "category_name", "reviewer_name", "product_id", "review_id", "pred_label_vn", "content_display", "model", "ts"]
        else:
            display_cols = ["platform", "category_name", "reviewer_name", "product_id", "review_id", "pred_label", "content_display", "model", "ts"]
        
        available_cols = [col for col in display_cols if col in df_pred.columns]
        df_pred_display = df_pred[available_cols].fillna("")
        
        # Reset index to maintain order from MongoDB sort
        df_pred_display = df_pred_display.reset_index(drop=True)
        
        # Rename column for better display
        df_pred_display = df_pred_display.rename(columns={"content_display": "content"})
        
        # Add human readable timestamp column
        def _fmt_ts(v):
            import datetime
            try:
                if isinstance(v,(int,float)):
                    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(v)))
                # pymongo returns datetime for Spark current_timestamp()
                if hasattr(v, 'isoformat'):
                    return v.strftime("%Y-%m-%d %H:%M:%S")
                return str(v)
            except Exception:
                return str(v)
        if 'ts' in df_pred_display.columns and 'ts_human' not in df_pred_display.columns:
            df_pred_display['ts_human'] = df_pred_display['ts'].apply(_fmt_ts)
            # Put ts_human just before ts
            cols = list(df_pred_display.columns)
            if 'ts' in cols:
                cols.remove('ts_human'); insert_pos = cols.index('ts'); cols.insert(insert_pos, 'ts_human')
                df_pred_display = df_pred_display[cols]

        # Display predictions info and table
        total_pages_pred = max(1, math.ceil(total_predictions / st.session_state.pred_per_page))
        st.info(f"🔮 Showing {len(df_pred_display)} predictions | Page {st.session_state.pred_page}/{total_pages_pred} | Total: {total_predictions:,} | Last refresh: {time.strftime('%H:%M:%S')} ")
        st.dataframe(df_pred_display, use_container_width=True, height=400)
    else:
        st.warning("No predictions data available")

with console_tab:
    st.subheader("🖥️ System Console Logs")
    
    # Real-time system stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📥 Total Reviews", f"{db.reviews_raw.count_documents({}):,}")
    with col2:
        st.metric("🔮 Total Predictions", f"{db.reviews_pred.count_documents({}):,}")
    with col3:
        # Get recent activity (last 5 minutes)
        from datetime import datetime, timedelta
        five_min_ago = datetime.now() - timedelta(minutes=5)
        recent_count = db.reviews_raw.count_documents({"crawled_at": {"$gte": five_min_ago}})
        st.metric("🚀 Recent Activity (5min)", f"{recent_count}")
    
    # Recent crawler activity
    st.subheader("📡 Recent Crawler Activity")
    recent_reviews = list(db.reviews_raw.find()
                         .sort([("crawled_at", -1)])
                         .limit(10))
    
    if recent_reviews:
        log_data = []
        for review in recent_reviews:
            product_name = review.get("product_name", "N/A")
            if product_name and len(product_name) > 50:
                product_display = product_name[:50] + "..."
            else:
                product_display = product_name or "N/A"
                
            log_data.append({
                "Timestamp": review.get("crawled_at", "N/A"),
                "Platform": review.get("platform", "N/A"),
                "Category": review.get("category_name", "N/A"),
                "Product": product_display,
                "Reviewer": review.get("reviewer_name", "Anonymous"),
                "Rating": f"⭐ {review.get('rating', 'N/A')}"
            })
        st.dataframe(pd.DataFrame(log_data), use_container_width=True)
    else:
        st.info("🔄 Waiting for crawler activity...")
    
    # Recent prediction activity  
    st.subheader("🔮 Recent Prediction Activity")
    recent_predictions = list(db.reviews_pred.find()
                             .sort([("ts", -1)])
                             .limit(10))
    
    if recent_predictions:
        pred_log_data = []
        for pred in recent_predictions:
            # Get review details - use direct fields from prediction first, fallback to join
            review_id = pred.get("review_id")
            category_name = pred.get("category_name", "N/A")
            product_id = pred.get("product_id", "N/A")
            
            # Try to get product name from raw reviews
            review_detail = db.reviews_raw.find_one({"review_id": review_id}) if review_id else None
            if review_detail:
                product_name = review_detail.get("product_name", "N/A")
                if product_name and len(product_name) > 40:
                    product_display = product_name[:40] + "..."
                else:
                    product_display = product_name or "N/A"
                # Update category from raw if available
                if review_detail.get("category_name"):
                    category_name = review_detail.get("category_name")
            else:
                # No raw review found, use product_id as display
                product_display = f"Product {product_id}"
                
            pred_log_data.append({
                "Timestamp": pred.get("ts", "N/A"),
                "Review ID": str(review_id)[:12] + "..." if review_id else "N/A",
                "Category": category_name,
                "Product": product_display,
                "Prediction": pred.get("pred_label_vn", pred.get("pred", "N/A")),
                "Model": pred.get("model", "N/A")
            })
        st.dataframe(pd.DataFrame(pred_log_data), use_container_width=True)
    else:
        st.info("🔄 Waiting for prediction activity...")

with eval_tab:
    st.subheader("Manual Evaluation")
    
    # Initialize session state
    if 'eval_last_df' not in st.session_state:
        st.session_state.eval_last_df = None
    if 'eval_last_error' not in st.session_state:
        st.session_state.eval_last_error = None
    if 'eval_last_info' not in st.session_state:
        st.session_state.eval_last_info = None
    
    # Sampling controls
    col1, col2 = st.columns([3, 1])
    with col1:
        k = st.number_input("Sample size", 100, 5000, 1000, 100, help="Number of reviews to sample randomly")
    with col2:
        st.write("")  # Spacer
        st.write("")  # Spacer
        generate_click = st.button("🎲 Generate Sample", type="primary", use_container_width=True)
    
    if generate_click:
        try:
            cur = db.reviews_raw.aggregate([{ "$sample": { "size": int(k) } }])
            rows = list(cur)
        except Exception as e:
            st.session_state.eval_last_error = f"Mongo aggregation failed: {e}"
            st.error(st.session_state.eval_last_error)
            rows = []
        if not rows:
            st.session_state.eval_last_info = "No reviews available in database. Please crawl some data first."
            st.warning(st.session_state.eval_last_info)
        else:
            texts = [f"{r.get('title','')} {r.get('content','')}".strip() for r in rows]
            valid_data = [(r, t) for r, t in zip(rows, texts) if len(t) > 3]
            if not valid_data:
                st.session_state.eval_last_error = "No valid text data found in sampled reviews."
                st.error(st.session_state.eval_last_error)
            else:
                rows_filtered, texts_filtered = zip(*valid_data)
                try:
                    resp = requests.post(f"{INFER_URL}/predict", json={"texts": list(texts_filtered)}, timeout=60)
                    if resp.status_code != 200:
                        st.session_state.eval_last_error = f"Inference HTTP {resp.status_code}: {resp.text[:200]}"
                        st.error(st.session_state.eval_last_error)
                    else:
                        res = resp.json()
                        preds = res.get("pred")
                        if not preds:
                            st.session_state.eval_last_error = "Inference service returned no predictions."
                            st.error(st.session_state.eval_last_error)
                        else:
                            min_len = min(len(rows_filtered), len(preds))
                            def label_to_vietnamese(pred_label):
                                label_map = {0: "Không tốt", 1: "Tốt", 2: "Trung bình"}
                                return label_map.get(pred_label, f"Unknown({pred_label})")
                            
                            # Build dataframe with all necessary fields
                            product_names = []
                            product_names_full = []
                            product_ids = []
                            review_ids = []
                            
                            for r in rows_filtered[:min_len]:
                                # Store full product name
                                full_name = r.get("product_name", r.get("product_id", "Unknown"))
                                product_names_full.append(full_name)
                                
                                # Create display name (truncated)
                                pname = full_name
                                if pname and len(pname) > 40:
                                    pname = pname[:40] + "..."
                                product_names.append(pname)
                                
                                # Store product_id and review_id for queries
                                product_ids.append(r.get("product_id", ""))
                                review_ids.append(r.get("review_id", ""))
                            
                            df = pd.DataFrame({
                                "review_id": review_ids,
                                "product_id": product_ids,
                                "product_name": product_names,
                                "product_name_full": product_names_full,
                                "category_name": [r.get("category_name", "Unknown") for r in rows_filtered[:min_len]],
                                "pred_label": [label_to_vietnamese(p) for p in preds[:min_len]],
                                "pred_numeric": preds[:min_len]
                            })
                            st.session_state.eval_last_df = df
                            st.session_state.eval_last_error = None
                            st.session_state.eval_last_info = f"Sampled {min_len} reviews."
                except Exception as e:
                    st.session_state.eval_last_error = f"Error calling inference service: {e}"
                    st.error(st.session_state.eval_last_error)
    
    # Render previous successful sample if exists and no new error
    if st.session_state.eval_last_df is not None and st.session_state.eval_last_error is None:
        df = st.session_state.eval_last_df
        st.info(st.session_state.eval_last_info or "Sample ready")
        
        # Store full review data for detail view
        if 'eval_full_reviews' not in st.session_state:
            st.session_state.eval_full_reviews = {}
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top 10 Products by Reviews")
            top_products = df['product_name'].value_counts().head(10).index.tolist()
            df_top = df[df['product_name'].isin(top_products)]
            fig_prod = px.histogram(df_top, y="product_name", color="pred_label",
                                   labels={"pred_label": "Đánh giá", "count": "Số lượng"},
                                   color_discrete_map={"Tốt": "#2ecc71", "Trung bình": "#f39c12", "Không tốt": "#e74c3c"},
                                   category_orders={"pred_label": ["Tốt", "Trung bình", "Không tốt"]})
            fig_prod.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_prod, use_container_width=True)
        with c2:
            st.subheader("By category")
            fig_cat = px.histogram(df, x="category_name", color="pred_label",
                                  labels={"pred_label": "Đánh giá", "count": "Số lượng"},
                                  color_discrete_map={"Tốt": "#2ecc71", "Trung bình": "#f39c12", "Không tốt": "#e74c3c"},
                                  category_orders={"pred_label": ["Tốt", "Trung bình", "Không tốt"]})
            st.plotly_chart(fig_cat, use_container_width=True)
        
        # Top 10 Worst Products (most negative reviews)
        st.divider()
        st.subheader("🔻 Top 10 Worst Products (Most Negative Reviews)")
        
        # Count negative reviews per product
        df_negative = df[df['pred_label'] == 'Không tốt']
        if len(df_negative) > 0:
            negative_counts = df_negative['product_name'].value_counts().head(10)
            worst_products = negative_counts.index.tolist()
            
            # Create bar chart for worst products
            df_worst = pd.DataFrame({
                'product_name': negative_counts.index,
                'negative_count': negative_counts.values
            })
            
            fig_worst = px.bar(df_worst, x='negative_count', y='product_name',
                             orientation='h',
                             labels={'negative_count': 'Số đánh giá tiêu cực', 'product_name': 'Sản phẩm'},
                             color='negative_count',
                             color_continuous_scale=['#ffcccc', '#ff0000'])
            fig_worst.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
            st.plotly_chart(fig_worst, use_container_width=True)
            
            # Product selector for detailed reviews
            st.divider()
            st.subheader("📝 Review Details")
            
            # Search options
            search_type = st.radio("Search by:", ["Product Name", "Product ID"], horizontal=True)
            
            product_reviews = None
            
            if search_type == "Product Name":
                # Dropdown selector for product names (using full names for matching)
                product_names_unique = sorted(df['product_name_full'].unique().tolist())
                # Create display options (truncate if needed)
                display_options = ['-- Choose a product --']
                for pname in product_names_unique:
                    display_name = pname if len(pname) <= 50 else pname[:50] + "..."
                    display_options.append(display_name)
                
                selected_display = st.selectbox(
                    "Select product:",
                    options=display_options,
                    key='product_selector'
                )
                
                if selected_display and selected_display != '-- Choose a product --':
                    # Find the matching full product name
                    idx = display_options.index(selected_display) - 1  # -1 for the "Choose" option
                    selected_product_full = product_names_unique[idx]
                    
                    # Filter reviews for selected product using full name
                    product_reviews = df[df['product_name_full'] == selected_product_full]
                    st.caption(f"**Product:** {selected_product_full}")
            else:
                # Text input for product ID or partial name search
                search_query = st.text_input("Enter Product ID or partial Product Name:", key='product_search')
                
                if search_query:
                    # Try exact product_id match first
                    product_reviews = df[df['product_id'] == search_query]
                    
                    if len(product_reviews) == 0:
                        # Fallback to partial product_name_full match
                        product_reviews = df[df['product_name_full'].str.contains(search_query, case=False, na=False)]
                        
                    if len(product_reviews) == 0:
                        st.warning(f"No products found matching: {search_query}")
                        product_reviews = None
                    else:
                        # Show matched product info
                        matched_products = product_reviews['product_name_full'].unique()
                        st.caption(f"**Found {len(matched_products)} product(s):** {', '.join(matched_products[:3])}" + 
                                 (f" and {len(matched_products)-3} more..." if len(matched_products) > 3 else ""))
            
            # Display review details if a product is selected
            if product_reviews is not None and len(product_reviews) > 0:
                
                # Summary stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    total = len(product_reviews)
                    st.metric("Total Reviews", total)
                with col2:
                    good = len(product_reviews[product_reviews['pred_label'] == 'Tốt'])
                    st.metric("Tốt", good, delta=f"{good/total*100:.1f}%" if total > 0 else "0%")
                with col3:
                    neutral = len(product_reviews[product_reviews['pred_label'] == 'Trung bình'])
                    st.metric("Trung bình", neutral, delta=f"{neutral/total*100:.1f}%" if total > 0 else "0%")
                with col4:
                    bad = len(product_reviews[product_reviews['pred_label'] == 'Không tốt'])
                    st.metric("Không tốt", bad, delta=f"{bad/total*100:.1f}%" if total > 0 else "0%")
                
                # Show reviews in tabs by sentiment
                tab_good, tab_neutral, tab_bad = st.tabs(["✅ Tốt", "⚠️ Trung bình", "❌ Không tốt"])
                
                with tab_good:
                    good_reviews = product_reviews[product_reviews['pred_label'] == 'Tốt']
                    if len(good_reviews) > 0:
                        st.info(f"Showing {len(good_reviews)} positive reviews")
                        # Get full review content from MongoDB using review_id
                        for idx, row in good_reviews.iterrows():
                            review_doc = db.reviews_raw.find_one({"review_id": row['review_id']})
                            if review_doc:
                                with st.expander(f"⭐ {review_doc.get('rating', 'N/A')} - {review_doc.get('reviewer_name', 'Anonymous')}"):
                                    st.write(f"**Title:** {review_doc.get('title', 'N/A')}")
                                    st.write(f"**Content:** {review_doc.get('content', 'N/A')}")
                                    st.caption(f"Product ID: {row['product_id']} | Category: {row['category_name']} | Created: {review_doc.get('create_time', 'N/A')}")
                            else:
                                st.warning(f"Review {row['review_id']} not found in database")
                    else:
                        st.info("No positive reviews found")
                
                with tab_neutral:
                    neutral_reviews = product_reviews[product_reviews['pred_label'] == 'Trung bình']
                    if len(neutral_reviews) > 0:
                        st.info(f"Showing {len(neutral_reviews)} neutral reviews")
                        for idx, row in neutral_reviews.iterrows():
                            review_doc = db.reviews_raw.find_one({"review_id": row['review_id']})
                            if review_doc:
                                with st.expander(f"⭐ {review_doc.get('rating', 'N/A')} - {review_doc.get('reviewer_name', 'Anonymous')}"):
                                    st.write(f"**Title:** {review_doc.get('title', 'N/A')}")
                                    st.write(f"**Content:** {review_doc.get('content', 'N/A')}")
                                    st.caption(f"Product ID: {row['product_id']} | Category: {row['category_name']} | Created: {review_doc.get('create_time', 'N/A')}")
                            else:
                                st.warning(f"Review {row['review_id']} not found in database")
                    else:
                        st.info("No neutral reviews found")
                
                with tab_bad:
                    bad_reviews = product_reviews[product_reviews['pred_label'] == 'Không tốt']
                    if len(bad_reviews) > 0:
                        st.info(f"Showing {len(bad_reviews)} negative reviews")
                        for idx, row in bad_reviews.iterrows():
                            review_doc = db.reviews_raw.find_one({"review_id": row['review_id']})
                            if review_doc:
                                with st.expander(f"⭐ {review_doc.get('rating', 'N/A')} - {review_doc.get('reviewer_name', 'Anonymous')}"):
                                    st.write(f"**Title:** {review_doc.get('title', 'N/A')}")
                                    st.write(f"**Content:** {review_doc.get('content', 'N/A')}")
                                    st.caption(f"Product ID: {row['product_id']} | Category: {row['category_name']} | Created: {review_doc.get('create_time', 'N/A')}")
                            else:
                                st.warning(f"Review {row['review_id']} not found in database")
                    else:
                        st.info("No negative reviews found")
        else:
            st.warning("No negative reviews found in the sample")
        
        st.divider()
        st.subheader("📊 Sample Data Table")
        st.dataframe(df[["product_name", "category_name", "pred_label"]].head(50), use_container_width=True)
    elif st.session_state.eval_last_error:
        st.error(st.session_state.eval_last_error)
    elif st.session_state.eval_last_info:
        st.warning(st.session_state.eval_last_info)

# Auto-refresh functionality
if auto_refresh:
    st.session_state.refresh_counter += 1
    time.sleep(REFRESH_INTERVAL)
    st.rerun()
