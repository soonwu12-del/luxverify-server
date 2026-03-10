import asyncio
import logging
import re
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def scrape_kream(keyword: str) -> dict:
    """
    크림(KREAM) 검색 결과에서 실시간 시세 추출
    - 즉시구매가 기준
    - 최근 체결가 기준
    """
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
        )
        page = await context.new_page()

        # 봇 탐지 우회
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        try:
            url = f"https://kream.co.kr/search?keyword={keyword}&sort=popular"
            logger.info(f"[Kream] 요청: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # 상품 카드 로딩 대기
            await page.wait_for_selector(".search_result_item, .product_card, [class*='product']", timeout=10000)

            # 상품 카드에서 이름 + 가격 추출
            items = await page.evaluate("""
                () => {
                    const results = [];
                    // 상품 카드 셀렉터 (크림 구조에 맞게)
                    const cards = document.querySelectorAll('.search_result_item');
                    cards.forEach(card => {
                        const nameEl   = card.querySelector('.translated_name, .product_name, [class*="name"]');
                        const priceEl  = card.querySelector('.amount, [class*="price"] .amount, [class*="price"]');
                        const brandEl  = card.querySelector('.brand_name, [class*="brand"]');

                        const name  = nameEl  ? nameEl.innerText.trim()  : '';
                        const brand = brandEl ? brandEl.innerText.trim() : '';
                        const priceRaw = priceEl ? priceEl.innerText.trim() : '';

                        // 숫자만 추출
                        const price = parseInt(priceRaw.replace(/[^0-9]/g, ''));

                        if (name && price > 0) {
                            results.push({ name, brand, price, priceRaw });
                        }
                    });
                    return results;
                }
            """)

            # 가격 유효성 필터
            results = [
                item for item in items
                if isinstance(item.get("price"), int)
                and 10000 <= item["price"] < 100000000
            ]

            logger.info(f"[Kream] '{keyword}' → {len(results)}개 수집")

        except Exception as e:
            logger.error(f"[Kream] 오류: {e}")
        finally:
            await browser.close()

    return _calc_stats(results, "kream")


def _calc_stats(items: list, source: str) -> dict:
    if not items:
        return {"source": source, "count": 0, "items": [], "min": 0, "max": 0, "avg": 0, "mid": 0}

    prices = sorted([i["price"] for i in items])
    n      = len(prices)
    total  = sum(prices)
    mid    = prices[n // 2]
    avg    = total // n
    mn     = prices[0]
    mx     = prices[-1]

    # 이상치 제거 (상하 20% 제외)
    trimmed = prices[int(n*0.2): int(n*0.8)+1] or prices
    trimmed_avg = sum(trimmed) // len(trimmed)

    return {
        "source":       source,
        "count":        n,
        "min":          mn,
        "max":          mx,
        "avg":          avg,
        "mid":          mid,
        "trimmed_avg":  trimmed_avg,  # 추천 기준가
        "items":        items[:10],
    }
