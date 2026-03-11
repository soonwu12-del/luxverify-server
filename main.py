from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio, logging, os, json, re
from scraper_kream import scrape_kream
from scraper_bunjang import scrape_bunjang

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 LuxVerify Price Server starting...")
    yield
    logger.info("Server shutting down")

app = FastAPI(title="LuxVerify Price API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
    max_age=86400,
)

@app.get("/")
def root():
    return {"status": "ok", "service": "LuxVerify Price API"}

@app.get("/api/price")
async def get_price(q: str = Query(...)):
    logger.info(f"[API] 검색: {q}")
    kream_task = asyncio.create_task(scrape_kream(q))
    bunjang_task = asyncio.create_task(scrape_bunjang(q))
    kream_result, bunjang_result = await asyncio.gather(kream_task, bunjang_task, return_exceptions=True)
    if isinstance(kream_result, Exception):
        kream_result = {"error": str(kream_result), "items": []}
    if isinstance(bunjang_result, Exception):
        bunjang_result = {"error": str(bunjang_result), "items": []}
    return {"keyword": q, "kream": kream_result, "bunjang": bunjang_result}

@app.get("/api/kream")
async def get_kream(q: str = Query(...)):
    result = await scrape_kream(q)
    return {"keyword": q, **result}

@app.get("/api/bunjang")
async def get_bunjang(q: str = Query(...)):
    result = await scrape_bunjang(q)
    return {"keyword": q, **result}

@app.get("/api/crawl")
async def crawl_daangn(url: str = Query(...)):
    import httpx
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
            html = res.text
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            return {"crawlFailed": True}
        data = json.loads(m.group(1))
        props = data.get("props", {}).get("pageProps", {})
        article = props.get("article") or props.get("product") or props.get("item") or props.get("articlePayload") or {}
        if not article:
            for v in props.values():
                if isinstance(v, dict) and ("price" in v or "title" in v):
                    article = v
                    break
        title = article.get("title") or article.get("name") or ""
        try:
            price = int(str(article.get("price") or article.get("priceAmount") or 0).replace(",", "").replace("원", "").strip())
        except Exception:
            price = 0
        desc = article.get("content") or article.get("description") or article.get("body") or ""
        images = []
        for key in ["images", "thumbnails", "photos"]:
            val = article.get(key)
            if isinstance(val, list):
                for img in val:
                    if isinstance(img, dict):
                        src = img.get("url") or img.get("src") or ""
                    elif isinstance(img, str):
                        src = img
                    else:
                        src = ""
                    if src:
                        images.append(src)
                break
        image = images[0] if images else (article.get("thumbnail") or article.get("firstImage") or "")
        seller = props.get("seller") or props.get("author") or props.get("user") or {}
        return {
            "title": title,
            "price": price,
            "description": desc,
            "image": image,
            "images": images[:8],
            "mannerTemp": seller.get("mannerTemperature") or seller.get("temperature"),
            "sellerName": seller.get("nickname", ""),
            "condition": "used",
            "crawlFailed": not bool(title or price),
        }
    except Exception as e:
        logger.error(f"[Crawl] 오류: {e}")
        return {"crawlFailed": True}
