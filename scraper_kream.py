import asyncio
import re
import os
from playwright.async_api import async_playwright

KREAM_TOKEN         = os.environ.get("KREAM_TOKEN", "")
KREAM_REFRESH_TOKEN = os.environ.get("KREAM_REFRESH_TOKEN", "")
KREAM_USER_ID       = os.environ.get("KREAM_USER_ID", "")

async def scrape_kream(keyword: str) -> dict:
    result = {
        "count": 0,
        "min": 0,
        "max": 0,
        "avg": 0,
        "mid": 0,
        "instant_sell_price": None,
        "trade_interval_days": None,
        "trade_interval_desc": None,
        "items": [],
        "trade_history": []
    }

    if not KREAM_TOKEN:
        print("[Kream] 토큰 없음 - 스킵")
        return result

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            viewport={"width": 390, "height": 844},
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"}
        )

        cookies = [
            {"name": "_token.local.p-2",        "value": KREAM_TOKEN,         "domain": "kream.co.kr", "path": "/"},
            {"name": "_refresh_token.local.p-2", "value": KREAM_REFRESH_TOKEN, "domain": "kream.co.kr", "path": "/"}
        ]
        if KREAM_USER_ID:
            cookies.append({"name": "ab.storage.userId.a45e84", "value": KREAM_USER_ID, "domain": "kream.co.kr", "path": "/"})
        await ctx.add_cookies(cookies)

        page = await ctx.new_page()

        try:
            search_url = "https://kream.co.kr/search?keyword=" + keyword
            print("[Kream] 검색: " + search_url)
            await page.goto(search_url, timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            first = page.locator(".search_result_item, .item_inner").first
            if not await first.is_visible():
                print("[Kream] 상품 없음")
                await browser.close()
                return result
            await first.click()
            await page.wait_for_timeout(2500)
            print("[Kream] 상품 페이지: " + page.url)

            try:
                sell_btn = page.locator("button:has-text('즉시 판매'), a:has-text('즉시 판매')").first
                if await sell_btn.is_visible():
                    await sell_btn.click()
                    await page.wait_for_timeout(2000)
                    price_el = page.locator(".instant_price, [class*='instant'] [class*='price']").first
                    if await price_el.is_visible():
                        raw = await price_el.text_content()
                        cleaned = int(re.sub(r"[^\d]", "", raw))
                        if cleaned > 0:
                            result["instant_sell_price"] = cleaned
                            print("[Kream] 즉시판매가: " + str(cleaned))
                    await page.go_back()
                    await page.wait_for_timeout(1500)
            except Exception as e:
                print("[Kream] 즉시판매가 실패: " + str(e))

            try:
                for sel in ["text=체결 내역", "button:has-text('체결')"]:
                    tab = page.locator(sel).first
                    if await tab.is_visible():
                        await tab.click()
                        await page.wait_for_timeout(2000)
                        break
            except Exception as e:
                print("[Kream] 체결탭 실패: " + str(e))

            try:
                rows = []
                for sel in [".buy_sell_item", "[class*='history'] [class*='item']", ".list_item"]:
                    rows = await page.locator(sel).all()
                    if len(rows) > 0:
                        break

                trades = []
                for row in rows[:40]:
                    try:
                        text = await row.text_content()
                        if not text:
                            continue
                        text = text.strip()
                        skip = False
                        for w in ["95점", "번개", "보관판매", "STORAGE"]:
                            if w in text:
                                skip = True
                                break
                        if skip:
                            continue
                        pm = re.search(r"([\d,]+)\s*원", text)
                        if not pm:
                            continue
                        price = int(re.sub(r"[^\d]", "", pm.group(1)))
                        if price < 10000:
                            continue
                        date_str = None
                        for pat in [r"(\d{4}/\d{2}/\d{2})", r"(\d{2}/\d{2})", r"(\d+일\s*전)", r"(\d+시간\s*전)"]:
                            dm = re.search(pat, text)
                            if dm:
                                date_str = dm.group(1)
                                break
                        trades.append({"price": price, "date": date_str, "raw": text[:60]})
                    except Exception:
                        continue

                result["trade_history"] = trades[:15]
                result["count"] = len(trades)

                if len(trades) >= 2:
                    prices = sorted([t["price"] for t in trades])
                    result["min"] = prices[0]
                    result["max"] = prices[-1]
                    result["avg"] = round(sum(prices) / len(prices))
                    result["mid"] = prices[len(prices) // 2]
                    result["items"] = [{"name": keyword, "price": p} for p in prices[:10]]

                day_trades = []
                for t in trades:
                    if t["date"]:
                        m = re.search(r"(\d+)일\s*전", str(t["date"]))
                        if m:
                            day_trades.append(int(m.group(1)))
                        elif "시간 전" in str(t["date"]) or "분 전" in str(t["date"]):
                            day_trades.append(0)

                if len(day_trades) >= 3:
                    day_trades.sort()
                    intervals = [day_trades[i+1] - day_trades[i] for i in range(len(day_trades)-1) if day_trades[i+1] - day_trades[i] >= 0]
                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        result["trade_interval_days"] = round(avg_interval, 1)
                        if avg_interval <= 1:
                            result["trade_interval_desc"] = "하루 1회 이상 거래 🔥 — 입찰판매 강력 추천"
                        elif avg_interval <= 3:
                            result["trade_interval_desc"] = "평균 " + str(round(avg_interval, 1)) + "일마다 거래 👍 — 입찰판매 유리"
                        elif avg_interval <= 7:
                            result["trade_interval_desc"] = "평균 " + str(round(avg_interval, 1)) + "일마다 거래 📦 — 상황 따라 판단"
                        else:
                            result["trade_interval_desc"] = "평균 " + str(round(avg_interval, 1)) + "일마다 거래 😐 — 즉시판매 고려"

            except Exception as e:
                print("[Kream] 체결수집 실패: " + str(e))

        except Exception as e:
            print("[Kream] 전체 오류: " + str(e))
        finally:
            await browser.close()

    return result
