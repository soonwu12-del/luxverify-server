from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio, logging, json, re
from scraper_kream import scrape_kream
from scraper_bunjang import scrape_bunjang
from openai import AsyncOpenAI

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
    k, b = await asyncio.gather(scrape_kream(q), scrape_bunjang(q), return_exceptions=True)
    if isinstance(k, Exception): k = {"error": str(k), "items": []}
    if isinstance(b, Exception): b = {"error": str(b), "items": []}
    return {"keyword": q, "kream": k, "bunjang": b}

@app.get("/api/kream")
async def get_kream(q: str = Query(...)):
    return {"keyword": q, **(await scrape_kream(q))}

@app.get("/api/bunjang")
async def get_bunjang(q: str = Query(...)):
    return {"keyword": q, **(await scrape_bunjang(q))}

@app.get("/api/proxy")
async def proxy(url: str = Query(...)):
    import httpx
    headers = {
        "User-Agent": "Mozilla/5.0 (Android 13; Mobile) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://m.bunjang.co.kr/",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
        return res.json()
    except Exception as e:
        logger.error(f"[Proxy] 오류: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/gpt")
async def gpt_proxy(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    messages = body.get("messages", [])
    model = body.get("model", "gpt-4o-mini")
    max_tokens = body.get("max_tokens", 1500)
    temperature = body.get("temperature", 0.7)
    api_key = body.get("api_key", "").strip()
    if not messages:
        return JSONResponse({"error": "messages is required"}, status_code=400)
    if not api_key:
        return JSONResponse({"error": "api_key is required"}, status_code=400)
    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )
        content = resp.choices[0].message.content
        logger.info(f"[GPT] OK tokens={resp.usage.total_tokens}")
        return {"choices": [{"message": {"content": content}}]}
    except Exception as e:
        logger.error(f"[GPT] 오류: {type(e).__name__}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/crawl")
async def crawl_daangn(url: str = Query(...)):
    import httpx
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', res.text, re.DOTALL)
        if not m:
            return {"crawlFailed": True}
        data = json.loads(m.group(1))
        props = data.get("props", {}).get("pageProps", {})
        article = (
            props.get("article") or props.get("product") or
            props.get("item") or props.get("articlePayload") or {}
        )
        if not article:
            for v in props.values():
                if isinstance(v, dict) and ("price" in v or "title" in v):
                    article = v
                    break
        title = article.get("title") or article.get("name") or ""
        try:
            price = int(str(article.get("price") or article.get("priceAmount") or 0)
                        .replace(",", "").replace("원", "").strip())
        except:
            price = 0
        desc = article.get("content") or article.get("description") or ""
        images = []
        for key in ["images", "thumbnails", "photos"]:
            val = article.get(key)
            if isinstance(val, list):
                for img in val:
                    src = img.get("url", "") if isinstance(img, dict) else (img if isinstance(img, str) else "")
                    if src:
                        images.append(src)
                break
        image = images[0] if images else (article.get("thumbnail") or "")
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

