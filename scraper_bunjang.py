import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def scrape_bunjang(keyword: str) -> dict:
    """
    번개장터 검색 결과에서 실시간 매물 시세 추출
    - 판매 중인 매물 기준
    - 최신순 정렬
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
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="ko-KR",
        )
        page = await context.new_page()

        # 봇 탐지 우회
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        try:
            # 모바일 번개장터 검색 (봇 차단이 덜함)
            url = f"https://m.bunjang.co.kr/search/products?q={keyword}&order=date"
            logger.info(f"[Bunjang] 요청: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # 상품 목록 대기
            await page.wait_for_selector("[class*='productCard'], [class*='product-item'], [class*='item']", timeout=10000)

            items = await page.evaluate("""
                () => {
                    const results = [];
                    // 번개장터 모바일 상품 카드
                    const selectors = [
                        '[class*="productCard"]',
                        '[class*="product-card"]',
                        '[class*="ProductCard"]',
                        'li[class*="item"]',
                    ];

                    let cards = [];
                    for (const sel of selectors) {
                        cards = document.querySelectorAll(sel);
                        if (cards.length > 2) break;
                    }

                    cards.forEach(card => {
                        // 이름
                        const nameEl  = card.querySelector('[class*="name"], [class*="title"], p, h3, h4');
                        // 가격
                        const priceEl = card.querySelector('[class*="price"], [class*="Price"]');
                        // 판매완료 여부
                        const soldEl  = card.querySelector('[class*="sold"], [class*="Sold"], [class*="complete"]');

                        if (soldEl) return; // 판매완료 제외

                        const name     = nameEl  ? nameEl.innerText.trim()  : '';
                        const priceRaw = priceEl ? priceEl.innerText.trim() : '';
                        const price    = parseInt(priceRaw.replace(/[^0-9]/g, ''));

                        if (name && price >= 10000) {
                            results.push({ name, price, priceRaw });
                        }
                    });
                    return results;
                }
            """)

            # 필터링
            results = [
                item for item in items
                if isinstance(item.get("price"), int)
                and 10000 <= item["price"] < 100000000
            ]

            # 부족하면 API도 시도
            if len(results) < 3:
                logger.info("[Bunjang] 웹 파싱 부족, API 시도...")
                results = await _scrape_bunjang_api(keyword, page)

            logger.info(f"[Bunjang] '{keyword}' → {len(results)}개 수집")

        except Exception as e:
            logger.error(f"[Bunjang] 오류: {e}")
            # fallback: API 직접 호출
            try:
                results = await _scrape_bunjang_api(keyword, page)
            except Exception as e2:
                logger.error(f"[Bunjang] API fallback 오류: {e2}")
        finally:
            await browser.close()

    return _calc_stats(results, "bunjang")


async def _scrape_bunjang_api(keyword: str, page) -> list:
    """번개장터 내부 API 직접 호출"""
    import json

    api_url = f"https://api.bunjang.co.kr/api/1/find_v2.json?q={keyword}&order=date&page=0&n=20&stat=N"
    
    response = await page.evaluate(f"""
        async () => {{
            try {{
                const res = await fetch('{api_url}', {{
                    headers: {{
                        'Accept': 'application/json',
                        'Referer': 'https://m.bunjang.co.kr',
                    }}
                }});
                return await res.text();
            }} catch(e) {{
                return null;
            }}
        }}
    """)

    if not response:
        return []

    try:
        data  = json.loads(response)
        items_raw = data.get("list", [])
        results = []
        for item in items_raw:
            price = int(item.get("price", 0))
            name  = item.get("name", "")
            # 판매완료(status=2) 제외
            if item.get("status") == "2":
                continue
            if name and 10000 <= price < 100000000:
                results.append({"name": name, "price": price, "priceRaw": f"{price:,}원"})
        return results
    except Exception as e:
        logger.error(f"[Bunjang API] 파싱 오류: {e}")
        return []


def _calc_stats(items: list, source: str) -> dict:
    if not items:
        return {"source": source, "count": 0, "items": [], "min": 0, "max": 0, "avg": 0, "mid": 0, "trimmed_avg": 0}

    prices  = sorted([i["price"] for i in items])
    n       = len(prices)
    mid     = prices[n // 2]
    avg     = sum(prices) // n
    mn      = prices[0]
    mx      = prices[-1]

    trimmed     = prices[int(n*0.2): int(n*0.8)+1] or prices
    trimmed_avg = sum(trimmed) // len(trimmed)

    return {
        "source":      source,
        "count":       n,
        "min":         mn,
        "max":         mx,
        "avg":         avg,
        "mid":         mid,
        "trimmed_avg": trimmed_avg,
        "items":       items[:10],
    }
