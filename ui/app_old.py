import streamlit as st, pandas as pd, time, requests, os
from pymongo import MongoClient
import plotly.express as px
import math

API_BASE = os.getenv("API_BASE","http://api:8000")
MONGO_URI = os.getenv("MONGO_URI","mongodb://mongo:27017")
INFER_URL = os.getenv("INFER_URL","http://phobert-infer:5000")

st.set_page_config(page_title="VN Sentiment Realtime", layout="wide")
st.title("📊 VN Product Sentiment — Realtime Control")

# Session state for pagination
if 'reviews_page' not in st.session_state:
    st.session_state.reviews_page = 1
if 'pred_page' not in st.session_state:
    st.session_state.pred_page = 1
if 'reviews_per_page' not in st.session_state:
    st.session_state.reviews_per_page = 20
if 'pred_per_page' not in st.session_state:
    st.session_state.pred_per_page = 20
if 'logs_page' not in st.session_state:
    st.session_state.logs_page = 1
if 'logs_per_page' not in st.session_state:
    st.session_state.logs_per_page = 50

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info()  # Force connection
    db = client["reviews_db"]  # Use reviews_db to match Spark job
except Exception as e:
    st.error(f"Cannot connect to MongoDB: {e}")
    st.stop()

with st.sidebar:
    st.subheader("HTML Crawl (Shopee, no API)")
    shop_links_html = st.text_area("Shop links (one per line)", "https://shopee.vn/olay_officialstorevn#product_list")
    max_products_html = st.number_input("Max products (HTML)", 10, 2000, 100, 10)
    days_back_html = st.number_input("Days back (HTML)", 1, 3650, 365, 1)
    c = st.columns(4)
    if c[0].button("Start HTML Crawl"):
        payload = {"shop_links": [s.strip() for s in shop_links_html.splitlines() if s.strip()],
                   "max_products": int(max_products_html), "days_back": int(days_back_html)}
        r = requests.post(f"{API_BASE}/crawl/html/start", json=payload); st.success(r.json())
    if c[1].button("Pause"): st.info(requests.post(f"{API_BASE}/crawl/html/pause").json())
    if c[2].button("Resume"): st.info(requests.post(f"{API_BASE}/crawl/html/resume").json())
    if c[3].button("Stop"): st.warning(requests.post(f"{API_BASE}/crawl/html/stop").json())

    st.subheader("Tiki Crawler")
    st.write("Support URLs:")
    st.write("• Brand: `tiki.vn/thuong-hieu/brand-name.html`")
    st.write("• Store: `tiki.vn/cua-hang/store-name`") 
    st.write("• Category: `tiki.vn/category-name/c1234`")
    
    tiki_urls = st.text_area("Tiki URLs (one per line)", 
                             "https://tiki.vn/thuong-hieu/nan.html\nhttps://tiki.vn/thuong-hieu/huggies.html")
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

live_tab, pred_tab, eval_tab, logs_tab = st.tabs(["🟢 Live Reviews", "🔮 Live Predictions", "📈 Evaluation", "🧾 Logs"]) 

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
        if st.button("↻ Refresh", key="refresh_reviews"):
            st.rerun()
    
    # Live Reviews Data Processing
    total_reviews = db.reviews_raw.count_documents({})
    skip_reviews = (st.session_state.reviews_page - 1) * st.session_state.reviews_per_page
    raw = list(db.reviews_raw.find()
              .sort([("_id", -1)])  # Newest first
              .skip(skip_reviews)
              .limit(st.session_state.reviews_per_page))
    
    # Process and display reviews data
    if raw:
        df_raw = pd.DataFrame(raw)
        if "platform" in df_raw.columns:
            display_cols = ["platform", "reviewer_name", "product_name", "rating", "content", "create_time"]
            available_cols = [col for col in display_cols if col in df_raw.columns]
            # Debug: Show available columns
            st.sidebar.write(f"Debug - Available cols: {available_cols}")
            st.sidebar.write(f"Debug - All DataFrame cols: {list(df_raw.columns)}")
            df_raw = df_raw[available_cols].fillna("")
            
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
    
    # Placeholders for predictions
    pred_info_ph = st.empty()
    pred_table_ph = st.empty()
with eval_tab:
    st.write("Run evaluation against latest 1k samples using PhoBERT (offline inference call)")
    k = st.number_input("Sample n", 100, 5000, 1000, 100)
    if st.button("Run Evaluate"):
        cur = db.reviews_raw.aggregate([{ "$sample": { "size": int(k) } }])
        rows = list(cur)
        texts = [f"{r.get('title','')} {r.get('content','')}".strip() for r in rows]
        if texts:
            res = requests.post(f"{INFER_URL}/predict", json={"texts": texts}).json()
            preds = res.get("pred", [])
            df = pd.DataFrame({"product_id":[r.get("product_id") for r in rows],
                               "category_id":[r.get("category_id") for r in rows],
                               "pred": preds})
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("By product")
                st.plotly_chart(px.histogram(df, x="product_id", color="pred"), use_container_width=True)
            with c2:
                st.subheader("By category")
                st.plotly_chart(px.histogram(df, x="category_id", color="pred"), use_container_width=True)
            st.dataframe(df.head(50), use_container_width=True)

with logs_tab:
    st.write("Crawler logs (HTML mode)")
    
    # Controls for logs pagination
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        logs_per_page = st.selectbox("Rows per page", [20, 50, 100, 200], 
                                     index=[20, 50, 100, 200].index(st.session_state.logs_per_page),
                                     key="logs_rows_select")
        st.session_state.logs_per_page = logs_per_page
    with col2:
        logs_page_input = st.number_input("Page", min_value=1, value=st.session_state.logs_page, 
                                         step=1, key="logs_page_input")
        if logs_page_input != st.session_state.logs_page:
            st.session_state.logs_page = logs_page_input
            st.rerun()
    
    # Placeholders for logs
    logs_info_ph = st.empty()
    log_area = st.empty()

# Create sidebar placeholder for model breakdown (outside loop)
st.sidebar.subheader("Model Breakdown")
model_chart_placeholder = st.sidebar.empty()

# refresh loop
while True:
    try:
        # Fetch all data sorted by newest first (_id descending for MongoDB default)
        total_reviews = db.reviews_raw.count_documents({})
        total_predictions = db.reviews_pred.count_documents({})
        
        # Get paginated data for reviews
        skip_reviews = (st.session_state.reviews_page - 1) * st.session_state.reviews_per_page
        raw = list(db.reviews_raw.find()
                  .sort([("_id", -1)])  # Newest first
                  .skip(skip_reviews)
                  .limit(st.session_state.reviews_per_page))
        
        # Get paginated data for predictions
        skip_pred = (st.session_state.pred_page - 1) * st.session_state.pred_per_page
        pred = list(db.reviews_pred.find()
                   .sort([("ts", -1)])  # Newest first by timestamp
                   .skip(skip_pred)
                   .limit(st.session_state.pred_per_page))
        
        # Process reviews data
        if raw:
            df_raw = pd.DataFrame(raw)
            if "platform" in df_raw.columns:
                display_cols = ["platform", "reviewer_name", "product_name", "rating", "content", "create_time"]
                available_cols = [col for col in display_cols if col in df_raw.columns]
                # Debug: Show available columns
                st.sidebar.write(f"Debug - Available cols: {available_cols}")
                st.sidebar.write(f"Debug - All DataFrame cols: {list(df_raw.columns)}")
                df_raw = df_raw[available_cols].fillna("")
                
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
            
            # Update reviews tab
            total_pages_reviews = max(1, math.ceil(total_reviews / st.session_state.reviews_per_page))
            reviews_info_ph.info(f"📊 Showing {len(df_raw)} reviews | Page {st.session_state.reviews_page}/{total_pages_reviews} | Total: {total_reviews:,}")
            reviews_table_ph.dataframe(df_raw, use_container_width=True, height=400)
        else:
            reviews_info_ph.warning("No reviews data available")
            reviews_table_ph.empty()
        
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
                # Fallback: try to get content from reviews_raw by product_id
                product_ids = df_pred['product_id'].unique().tolist() if 'product_id' in df_pred.columns else []
                content_map = {}
                if product_ids:
                    reviews_with_content = list(db.reviews_raw.find(
                        {"product_id": {"$in": product_ids}},
                        {"product_id": 1, "title": 1, "content": 1}
                    ).limit(100))
                    for rev in reviews_with_content:
                        pid = rev.get("product_id")
                        title = rev.get("title", "")
                        content = rev.get("content", "")
                        combined = f"{title} {content}".strip()
                        if pid and combined and pid not in content_map:  # Take first match only
                            content_map[pid] = combined[:100] + "..." if len(combined) > 100 else combined
                
                df_pred['content_display'] = df_pred['product_id'].map(content_map).fillna("N/A")
            
            # Check if pred_label_vn exists, otherwise fallback
            if "pred_label_vn" in df_pred.columns:
                display_cols = ["platform", "product_id", "rating", "pred_label_vn", "content_display", "model", "ts"]
            else:
                display_cols = ["platform", "product_id", "rating", "pred_label", "content_display", "model", "ts"]
            
            available_cols = [col for col in display_cols if col in df_pred.columns]
            df_pred_display = df_pred[available_cols].fillna("")
            
            # Rename column for better display
            df_pred_display = df_pred_display.rename(columns={"content_display": "content"})
            
            # Update predictions tab
            total_pages_pred = max(1, math.ceil(total_predictions / st.session_state.pred_per_page))
            pred_info_ph.info(f"🔮 Showing {len(df_pred_display)} predictions | Page {st.session_state.pred_page}/{total_pages_pred} | Total: {total_predictions:,}")
            pred_table_ph.dataframe(df_pred_display, use_container_width=True, height=400)
            
            # Update model breakdown chart
            model_chart_placeholder.bar_chart(df_pred.groupby(["model"]).size())
        else:
            pred_info_ph.warning("No predictions data available")
            pred_table_ph.empty()
        
        # Update logs
        total_logs = db.logs_html.count_documents({})
        skip_logs = (st.session_state.logs_page - 1) * st.session_state.logs_per_page
        logs = list(db.logs_html.find()
                   .sort([("_id", -1)])
                   .skip(skip_logs)
                   .limit(st.session_state.logs_per_page))
        if logs:
            df_logs = pd.DataFrame(logs)
            if "ts" in df_logs.columns and "level" in df_logs.columns and "msg" in df_logs.columns:
                df_logs = df_logs[["ts", "level", "msg"]].fillna("")
                
                # Update logs tab
                total_pages_logs = max(1, math.ceil(total_logs / st.session_state.logs_per_page))
                logs_info_ph.info(f"🧾 Showing {len(df_logs)} logs | Page {st.session_state.logs_page}/{total_pages_logs} | Total: {total_logs:,}")
                log_area.dataframe(df_logs, use_container_width=True, height=400)
        else:
            logs_info_ph.warning("No logs available")
            log_area.empty()
        
        time.sleep(2)  # Refresh every 2 seconds
        
    except Exception as e:
        st.caption(f"Waiting for data… {e}")
        time.sleep(3)
