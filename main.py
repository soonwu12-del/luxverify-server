from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging

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
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "service": "LuxVerify Price API"}

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
