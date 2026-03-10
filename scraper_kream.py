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
import asyncio, re, os
from playwright.async_api import async_playwright

KREAM_TOKEN         = os.environ.get("KREAM_TOKEN", "")
KREAM_REFRESH_TOKEN = os.environ.get("KREAM_REFRESH_TOKEN", "")
KREAM_USER_ID       = os.environ.get("KREAM_USER_ID", "")

async def scrape_kream(keyword: str) -> dict:
    result = {
        "count": 0, "min": 0, "max": 0, "avg": 0, "mid": 0,
        "instant_sell_price": None,
        "trade_interval_days": None,
        "trade_interval_desc": None,
        "items": [],
        "trade_history": []
    }

    if not KREAM_TOKEN:
        print("[Kream] 토큰 없음 — 스킵")
        return result

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            viewport={"width": 390, "height": 844},
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9",
            }
        )

        # ── 쿠키 주입 ──────────────────────────────────────────
        cookies = [
            {"name": "_token.local.p-2",         "value": KREAM_TOKEN,         "domain": "kream.co.kr", "path": "/"},
            {"name": "_refresh_token.local.p-2",  "value": KREAM_REFRESH_TOKEN, "domain": "kream.co.kr", "path": "/"},
        ]
        if KREAM_USER_ID:
            cookies.append({"name": "ab.storage.userId.a45e84", "value": KREAM_USER_ID, "domain": "kream.co.kr", "path": "/"})
        await ctx.add_cookies(cookies)

        page = await ctx.new_page()

        try:
            # ── 1) 검색 ────────────────────────────────────────
            search_url = f"https://kream.co.kr/search?keyword={keyword}"
            print(f"[Kream] 검색: {search_url}")
            await page.goto(search_url, timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            # 첫 번째 상품 클릭
            first = page.locator(".search_result_item, .item_inner, [class*='item']").first
            if not await first.is_visible():
                print("[Kream] 상품 없음")
                return result
            await first.click()
            await page.wait_for_timeout(2500)
            print(f"[Kream] 상품 페이지: {page.url}")

            # ── 2) 즉시판매가 ──────────────────────────────────
            try:
                sell_btn = page.locator("button:has-text('즉시 판매'), a:has-text('즉시 판매')").first
                if await sell_btn.is_visible():
                    await sell_btn.click()
                    await page.wait_for_timeout(2000)
                    # 즉시판매가 추출
                    price_el = page.locator(".instant_price, [class*='instant'] [class*='price'], .sell_now_price").first
                    if await price_el.is_visible():
                        raw = await price_el.text_content()
                        cleaned = int(re.sub(r"[^\d]", "", raw))
                        if cleaned > 0:
                            result["instant_sell_price"] = cleaned
                            print(f"[Kream] 즉시판매가: {cleaned}")
                    await page.go_back()
                    await page.wait_for_timeout(1500)
            except Exception as e:
                print(f"[Kream] 즉시판매가 추출 실패: {e}")

            # ── 3) 체결 내역 탭 ────────────────────────────────
            try:
                tab_selectors = [
                    "text=체결 내역",
                    "[class*='tab']:has-text('체결')",
                    "button:has-text('체결')"
                ]
                for sel in tab_selectors:
                    tab = page.locator(sel).first
                    if await tab.is_visible():
                        await tab.click()
                        await page.wait_for_timeout(2000)
                        print("[Kream] 체결 내역 탭 클릭")
                        break
            except Exception as e:
                print(f"[Kream] 체결 탭 클릭 실패: {e}")

            # ── 4) 체결 내역 수집 (95점·번개 제외) ────────────
            try:
                row_selectors = [
                    ".buy_sell_item",
                    "[class*='history'] [class*='item']",
                    "[class*='transaction'] [class*='row']",
                    ".list_item"
                ]
                rows = []
                for sel in row_selectors:
                    rows = await page.locator(sel).all()
                    if len(rows) > 0:
                        print(f"[Kream] 체결행 {len(rows)}개 ({sel})")
                        break

                trades = []
                for row in rows[:40]:
                    try:
                        text = await row.text_content()
                        if not text:
                            continue
                        text = text.strip()

                        # ❌ 보관판매 제외 (95점, 번개, 보관)
                        if any(x in text for x in ["95점", "⚡", "번개", "보관판매", "STORAGE"]):
                            print(f"[Kream] 보관판매 제외: {text[:40]}")
                            continue

                        # 가격 추출
                        price_match = re.search(r"([\d,]+)\s*원", text)
                        if not price_match:
                            continue
                        price = int(re.sub(r"[^\d]", "", price_match.group(1)))
                        if price < 10000:
                            continue

                        # 날짜 추출
                        date_str = None
                        date_patterns = [
                            r"(\d{4}/\d{2}/\d{2})",
                            r"(\d{2}/\d{2})",
                            r"(\d+일\s*전)",
                            r"(\d+시간\s*전)",
                            r"(\d+분\s*전)",
                        ]
                        for pat in date_patterns:
                            m = re.search(pat, text)
                            if m:
                                date_str = m.group(1)
                                break

                        trades.append({
                            "price": price,
                            "date":  date_str,
                            "raw":   text[:60]
                        })
                    except:
                        continue

                result["trade_history"] = trades[:15]
                result["count"] = len(trades)
                print(f"[Kream] 유효 체결 {len(trades)}개 (보관판매 제외)")

                # ── 5) 가격 통계 ───────────────────────────────
                if len(trades) >= 2:
                    prices = sorted([t["price"] for t in trades])
                    result["min"] = prices[0]
                    result["max"] = prices[-1]
                    result["avg"] = round(sum(prices) / len(prices))
                    result["mid"] = prices[len(prices) // 2]
                    result["items"] = [{"name": keyword, "price": p} for p in prices[:10]]

                # ── 6) 거래 주기 계산 ──────────────────────────
                # "N일 전" 패턴으로 주기 계산
                day_trades = []
                for t in trades:
                    if t["date"]:
                        m = re.search(r"(\d+)일\s*전", t["date"])
                        if m:
                            day_trades.append(int(m.group(1)))
                        elif "시간 전" in str(t["date"]) or "분 전" in str(t["date"]):
                            day_trades.append(0)

                if len(day_trades) >= 3:
                    day_trades.sort()
                    intervals = [day_trades[i+1] - day_trades[i]
                                 for i in range(len(day_trades)-1)
                                 if day_trades[i+1] - day_trades[i] >= 0]
                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        result["trade_interval_days"] = round(avg_interval, 1)

                        # 주기 설명
                        if avg_interval <= 1:
                            result["trade_interval_desc"] = "하루 1회 이상 거래 🔥 — 입찰판매 강력 추천"
                        elif avg_interval <= 3:
                            result["trade_interval_desc"] = f"평균 {avg_interval:.1f}일마다 거래 👍 — 입찰판매 유리"
                        elif avg_interval <= 7:
                            result["trade_interval_desc"] = f"평균 {avg_interval:.1f}일마다 거래 📦 — 입찰/즉시판매 상황 따라"
                        else:
                            result["trade_interval_desc"] = f"평균 {avg_interval:.1f}일마다 거래 😐 — 즉시판매 고려"

                        print(f"[Kream] 거래 주기: {result['trade_interval_desc']}")

            except Exception as e:
                print(f"[Kream] 체결 내역 수집 실패: {e}")

        except Exception as e:
            print(f"[Kream] 전체 오류: {e}")
        finally:
            await browser.close()

    return result
