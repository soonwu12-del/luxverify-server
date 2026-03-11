from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import json
import re

from scraper_kream import scrape_kream
from scraper_bunjang import scrape_bunjang

# ── OpenAI ──────────────────────────────────────────────────────────────────
from openai import AsyncOpenAI

openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "").strip().replace("\n", "").replace("\r", "").replace(" ", ""))


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
allow_credentials=False,
max_age=86400,

    allow_headers=["*"],
)

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "service": "LuxVerify Price API"}

# ── 가격 조회 ─────────────────────────────────────────────────────────────────
@app.get("/api/price")
async def get_price(q: str = Query(..., description="검색 키워드")):
    """크림 + 번개장터 동시 조회"""
    logger.info(f"[API] 검색: {q}")

    kream_task   = asyncio.create_task(scrape_kream(q))
    bunjang_task = asyncio.create_task(scrape_bunjang(q))

    kream_result, bunjang_result = await asyncio.gather(
        kream_task, bunjang_task, return_exceptions=True
    )

    if isinstance(kream_result, Exception):
        logger.error(f"크림 오류: {kream_result}")
        kream_result = {"error": str(kream_result), "items": []}

    if isinstance(bunjang_result, Exception):
        logger.error(f"번개장터 오류: {bunjang_result}")
        bunjang_result = {"error": str(bunjang_result), "items": []}

    return {
        "keyword": q,
        "kream":   kream_result,
        "bunjang": bunjang_result
    }

@app.get("/api/kream")
async def get_kream(q: str = Query(...)):
    """크림 단독 조회"""
    result = await scrape_kream(q)
    return {"keyword": q, **result}

@app.get("/api/bunjang")
async def get_bunjang(q: str = Query(...)):
    """번개장터 단독 조회"""
    result = await scrape_bunjang(q)
    return {"keyword": q, **result}

# ── GPT 프록시 (API 키 서버 보관) ──────────────────────────────────────────────
@app.post("/api/gpt")
async def gpt_proxy(request: Request):
    """
    OpenAI ChatCompletion 프록시.
    프론트엔드가 API 키 없이 GPT를 호출할 수 있도록 Railway 서버에서 중계.
    """
        api_key = os.environ.get("OPENAI_API_KEY", "").strip().replace("\n","").replace("\r","").replace(" ","")
    if not api_key:
        return JSONResponse({"error": "API key not configured on server"}, status_code=500)


    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    messages    = body.get("messages", [])
    model       = body.get("model", "gpt-4o-mini")
    max_tokens  = body.get("max_tokens", 1500)
    temperature = body.get("temperature", 0.7)

    if not messages:
        return JSONResponse({"error": "messages is required"}, status_code=400)

    try:
                client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(

            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = resp.choices[0].message.content
        logger.info(f"[GPT] model={model} tokens={resp.usage.total_tokens}")
        return {"choices": [{"message": {"content": content}}]}

    except Exception as e:
        logger.error(f"[GPT] 오류: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ── 당근마켓 크롤링 프록시 ────────────────────────────────────────────────────
@app.get("/api/crawl")
async def crawl_daangn(url: str = Query(..., description="당근마켓 상품 URL")):
    """
    Railway 서버에서 당근마켓 페이지를 크롤링하여 상품 정보를 반환.
    브라우저 CORS 우회용.
    """
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
            html = res.text

        # __NEXT_DATA__ 파싱
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            logger.warning(f"[Crawl] __NEXT_DATA__ 없음: {url}")
            return {"crawlFailed": True}

        data = json.loads(m.group(1))
        props = data.get("props", {}).get("pageProps", {})

        # article 객체 추출 (다양한 키 시도)
        article = (
            props.get("article")
            or props.get("product")
            or props.get("item")
            or props.get("articlePayload")
            or {}
        )
        if not article:
            for v in props.values():
                if isinstance(v, dict) and ("price" in v or "title" in v):
                    article = v
                    break

        # 제목
        title = article.get("title") or article.get("name") or ""

        # 가격
        price_raw = article.get("price") or article.get("priceAmount") or 0
        try:
            price = int(str(price_raw).replace(",", "").replace("원", "").strip())
        except Exception:
            price = 0

        # 설명
        desc = (
            article.get("content")
            or article.get("description")
            or article.get("body")
            or ""
        )

        # 이미지
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

        # 판매자
        seller = props.get("seller") or props.get("author") or props.get("user") or {}
        manner_temp = seller.get("mannerTemperature") or seller.get("temperature") or None

        result = {
            "title":      title,
            "price":      price,
            "description": desc,
            "image":      image,
            "images":     images[:8],
            "mannerTemp": manner_temp,
            "sellerName": seller.get("nickname", ""),
            "condition":  "used",
            "crawlFailed": not bool(title or price),
        }
        logger.info(f"[Crawl] 완료: '{title}' / {price:,}원")
        return result

    except Exception as e:
        logger.error(f"[Crawl] 오류: {e}")
        return {"crawlFailed": True}
