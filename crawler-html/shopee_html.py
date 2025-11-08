import os, time, asyncio, random, json
from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Response

MONGO_URI = os.getenv("MONGO_URI","mongodb://mongo:27017/?replicaSet=rs0")
RATE_PER_MIN = int(os.getenv("RATE_PER_MIN","60"))
HEADLESS = os.getenv("HEADLESS","1") == "1"
PROXY_LIST = [p.strip() for p in os.getenv("PROXY_LIST","").split(",") if p.strip()]

mongo = MongoClient(MONGO_URI)
db = mongo["reviews_db"]

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

def log(level: str, msg: str, extra: Optional[dict]=None):
    db.logs_html.insert_one({
        "ts": datetime.utcnow().isoformat()+"Z",
        "level": level,
        "msg": msg,
        **(extra or {})
    })

def get_ctrl():
    return db.system_status.find_one({"_id":"crawler_html_ctrl"}) or {}

def is_paused():
    return bool(get_ctrl().get("paused"))

def should_stop():
    return bool(get_ctrl().get("stop"))

def pick_proxy():
    if not PROXY_LIST: return None
    return random.choice(PROXY_LIST)

@asynccontextmanager
async def browser_ctx():
    async with async_playwright() as p:
        proxy = pick_proxy()
        launch_kwargs = {
            "headless": HEADLESS,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        }
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}
            log("info","using proxy", {"proxy": proxy})
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent=random.choice(UA_LIST), 
            locale="vi-VN",
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True
        )
        # Add stealth scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()

async def backoff_sleep(attempt: int, base: float = 1.0, cap: float = 30.0):
    t = min(cap, base * (2 ** attempt)) * (0.5 + random.random()/2)
    await asyncio.sleep(t)

async def get_product_links(shop_url: str, max_products: int = 200) -> List[str]:
    links: List[str] = []
    attempt = 0
    while True:
        try:
            async with browser_ctx() as ctx:
                page = await ctx.new_page()
                log("info", "navigating to shop", {"url": shop_url})
                await page.goto(shop_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)  # Wait for JS to load
                log("info", "page loaded", {"title": await page.title()})
                last_height = 0
                stalls = 0
                while len(links) < max_products and stalls < 8:
                    await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)
                    cards = await page.query_selector_all("a[href*='/product'], a[href*='/item'], a[href*='i.']")
                    log("info", f"found cards: {len(cards)}")
                    for c in cards:
                        href = await c.get_attribute("href")
                        if not href: continue
                        if ("/product/" in href) or ("/item/" in href):
                            url = href if href.startswith("http") else f"https://shopee.vn{href}"
                            if url not in links:
                                links.append(url)
                                if len(links) >= max_products:
                                    break
                    height = await page.evaluate("document.body.scrollHeight")
                    if height == last_height:
                        stalls += 1
                    else:
                        stalls = 0
                    last_height = height
                log("info","collected product links", {"n": len(links)})
                return links
        except Exception as e:
            log("error","get_product_links failed", {"error": str(e), "attempt": attempt})
            attempt += 1
            if attempt > 5: raise
            await backoff_sleep(attempt)

REV_KEYS = ("review","rating","comment","ratings")

async def scrape_reviews_via_network(page) -> List[dict]:
    collected: List[dict] = []
    async def on_response(res: Response):
        try:
            url = res.url
            ct = res.headers.get("content-type","")
            if "json" not in ct: return
            if not any(k in url for k in ("review","rating","comment")): return
            data = await res.json()
            js = json.dumps(data)
            if not any(k in js for k in REV_KEYS): return
            items = ((data.get("data") or {}).get("ratings") or data.get("ratings") or data.get("items") or [])
            for it in items:
                content = it.get("comment") or it.get("content") or ""
                rating = it.get("rating_star") or it.get("rating") or None
                ts = it.get("ctime") or it.get("create_time")
                iso = datetime.utcfromtimestamp(ts).isoformat()+"Z" if isinstance(ts,(int,float)) else (ts or datetime.utcnow().isoformat()+"Z")
                collected.append({"title":"", "content": content, "rating": rating, "create_time": iso})
        except Exception:
            pass
    page.on("response", on_response)
    return collected

async def scrape_reviews_via_dom(page, max_pages: int = 4) -> List[dict]:
    reviews = []
    for _ in range(max_pages):
        await page.wait_for_timeout(900)
        items = await page.query_selector_all("div[data-sqe='comment'], .shopee-product-rating")
        for it in items:
            try:
                content_el = await it.query_selector(".shopee-product-rating__main-comment, [data-sqe='comment-content']")
                content = (await content_el.inner_text()) if content_el else ""
                reviews.append({"title":"", "content":content, "rating": None, "create_time": datetime.utcnow().isoformat()+"Z"})
            except Exception:
                pass
        next_btn = await page.query_selector("button.shopee-icon-button--right, .shopee-button-no-outline")
        if not next_btn: break
        try:
            await next_btn.click(); await page.wait_for_timeout(900)
        except Exception:
            break
    return reviews

async def crawl_shop(shop_url: str, max_products: int = 100, days_back: int = 365):
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    product_links = await get_product_links(shop_url, max_products=max_products)
    async with browser_ctx() as ctx:
        for url in product_links:
            while (db.system_status.find_one({"_id":"crawler_html_ctrl"}) or {}).get("paused", False):
                await asyncio.sleep(1)
            if (db.system_status.find_one({"_id":"crawler_html_ctrl"}) or {}).get("stop", False):
                log("warn","stop requested"); return
            page = await ctx.new_page()
            attempt = 0
            try:
                await page.goto(url, wait_until="domcontentloaded")
                net_bucket = await scrape_reviews_via_network(page)
                await page.wait_for_timeout(1500)
                reviews = list(net_bucket) if net_bucket else await scrape_reviews_via_dom(page)
                product_id = url.split(".")[-1] if "." in url else url
                for rv in reviews:
                    try:
                        rv_time = datetime.fromisoformat(rv["create_time"].replace("Z",""))
                    except Exception:
                        rv_time = datetime.utcnow()
                    if rv_time < cutoff: continue
                    db.reviews_raw.insert_one({
                        "platform": "shopee",
                        "product_id": product_id,
                        "category_id": None,
                        "rating": rv.get("rating"),
                        "title": rv.get("title",""),
                        "content": rv.get("content",""),
                        "create_time": rv.get("create_time")
                    })
                log("info","pdp crawled", {"url": url, "n": len(reviews)})
            except Exception as e:
                log("error","pdp error", {"url": url, "error": str(e), "attempt": attempt})
                attempt += 1
                if attempt <= 5:
                    await backoff_sleep(attempt)
            finally:
                await page.close()
            await asyncio.sleep(max(60.0/RATE_PER_MIN, 0.2))

async def main_once():
    cfg = db.system_status.find_one({"_id":"crawler_html_cfg"}) or {}
    links: List[str] = cfg.get("shop_links") or []
    max_products = int(cfg.get("max_products", 100))
    days_back = int(cfg.get("days_back", 365))
    for link in links:
        log("info","start shop", {"link": link})
        await crawl_shop(link, max_products=max_products, days_back=days_back)
        log("info","done shop", {"link": link})

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main_once())
        except Exception as e:
            log("error","main loop", {"error": str(e)})
        time.sleep(5)
