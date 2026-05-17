import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import time
import base64

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from scraper import scrape_links
from checker import check_all_links
from suggester import process_suggestions
from database import save_scan

app = FastAPI(title="Broken Link Checker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://brokenlinkchecker-olive.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Screenshot cache ─────────────────────────────────────────────────────────
_preview_cache: dict[str, tuple[str, float]] = {}
_PREVIEW_CACHE_TTL = 600  # 10 minutes


def _calculate_health_score(results: list) -> int:
    total = len(results)
    if total == 0:
        return 100
    ok = sum(1 for r in results if r.label == "ok")
    broken_penalty = sum(3 for r in results if r.label == "broken")
    dead_cta_penalty = sum(2 for r in results if r.label == "dead_cta")
    timeout_penalty = sum(1 for r in results if r.label == "timeout")
    score = round((ok / total) * 100) - broken_penalty - dead_cta_penalty - timeout_penalty
    return max(0, min(100, score))


@app.get("/scan")
async def scan(
    url: str = Query(..., description="URL to scan"),
    email: str = Query(default="anonymous", description="User email for monitoring"),
):
    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Launching headless browser...', 'percent': 5})}\n\n"
            await asyncio.sleep(0.1)

            links = await scrape_links(url)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Found {len(links)} links. Checking each one...', 'percent': 30})}\n\n"
            await asyncio.sleep(0.1)

            results = []
            total = len(links)

            if total == 0:
                yield f"data: {json.dumps({'type': 'result', 'data': [], 'health_score': 100})}\n\n"
                return

            async for i, result in check_all_links(links):
                results.append(result)
                pct = 30 + int((i / total) * 55)
                yield f"data: {json.dumps({'type': 'progress', 'message': f'Checked {i}/{total} links...', 'percent': pct})}\n\n"

            # Run suggestion engine
            actionable_count = sum(1 for r in results if r.label in ["broken", "dead_cta", "blocked"])
            if actionable_count > 0:
                yield f"data: {json.dumps({'type': 'progress', 'message': f'Analyzing {actionable_count} links for suggestions...', 'percent': 90})}\n\n"
                await asyncio.sleep(0.1)
                results = await process_suggestions(results)

            # Calculate health score
            health_score = _calculate_health_score(results)

            # Save to Supabase (non-blocking — never fail the scan)
            try:
                await save_scan(
                    site_url=url,
                    user_email=email,
                    results=results,
                    health_score=health_score,
                )
            except Exception as db_err:
                print(f"[DB] Save failed (non-critical): {db_err}")

            yield f"data: {json.dumps({'type': 'result', 'data': [r.dict() for r in results], 'health_score': health_score})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/history")
async def history(
    url: str = Query(..., description="Site URL"),
    email: str = Query(default="anonymous", description="User email"),
):
    """Get scan history for a site."""
    try:
        from database import get_site_history
        data = await get_site_history(url, email)
        return {"url": url, "history": data}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/preview")
async def preview(url: str = Query(..., description="URL to screenshot")):
    now = time.time()

    if url in _preview_cache:
        cached_b64, cached_at = _preview_cache[url]
        if now - cached_at < _PREVIEW_CACHE_TTL:
            return JSONResponse({
                "url": url,
                "screenshot": cached_b64,
                "cached": True,
            })

    try:
        b64_png = await asyncio.to_thread(_capture_screenshot, url)
        _preview_cache[url] = (b64_png, now)

        expired = [
            k for k, (_, t) in _preview_cache.items()
            if now - t >= _PREVIEW_CACHE_TTL
        ]
        for k in expired:
            del _preview_cache[k]

        return JSONResponse({
            "url": url,
            "screenshot": b64_png,
            "cached": False,
        })
    except Exception as e:
        return JSONResponse({"url": url, "error": str(e)}, status_code=500)


def _capture_screenshot(url: str) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=10000)
            screenshot_bytes = page.screenshot(type="png")
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        finally:
            browser.close()


@app.get("/health")
async def health():
    return {"status": "ok"}