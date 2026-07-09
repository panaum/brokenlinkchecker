import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import time
import base64
import os
import httpx

from fastapi import FastAPI, Query
from models import LinkResult, SiteCreate
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from scraper import scrape_links
from checker import check_all_links
from suggester import process_suggestions
from database import save_scan
from sitemap import discover_site_urls

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


async def send_slack_notification(
    url: str,
    health_score: int,
    results: list
) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    total = len(results)
    working = sum(1 for r in results if r.label == "ok")
    broken = [r for r in results if r.label == "broken"]
    dead_cta = [r for r in results if r.label == "dead_cta"]
    redirects = sum(1 for r in results if r.label == "redirect")
    blocked = sum(1 for r in results if r.label == "blocked")

    if health_score >= 90:
        score_emoji = "✅"
    elif health_score >= 70:
        score_emoji = "⚠️"
    else:
        score_emoji = "🔴"

    # Build broken links text
    broken_text = ""
    if broken:
        lines = []
        for r in broken[:5]:
            path = r.url.replace("https://", "").replace("http://", "")
            path = "/" + "/".join(path.split("/")[1:]) if "/" in path else path
            lines.append(f"• `{path[:50]}` — {r.category}")
        if len(broken) > 5:
            lines.append(f"• ...and {len(broken) - 5} more")
        broken_text = "\n".join(lines)

    # Build dead CTAs text
    cta_text = ""
    if dead_cta:
        lines = []
        for r in dead_cta[:3]:
            anchor = r.anchor_text or "[no text]"
            # `zones` names the page regions the link sits in; source_element is
            # just the tag name and says nothing useful on its own.
            zones = getattr(r, "zones", None) or []
            where = ", ".join(zones) or getattr(r, "category", "") or "Unknown location"
            lines.append(f"• \"{anchor[:30]}\" — {where[:40]}")
        if len(dead_cta) > 3:
            lines.append(f"• ...and {len(dead_cta) - 3} more")
        cta_text = "\n".join(lines)

    # Build message blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔍 LinkSpy Scan Complete"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Site:*\n{url}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Health Score:*\n{health_score}/100 {score_emoji}"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Summary:*\n"
                    f"• Total links: {total}\n"
                    f"• ✅ Working: {working}\n"
                    f"• ❌ Broken: {len(broken)}\n"
                    f"• ⚠️ Dead CTAs: {len(dead_cta)}\n"
                    f"• 🔄 Redirects: {redirects}\n"
                    f"• 🔍 Can't verify: {blocked}"
                )
            }
        }
    ]

    if broken_text:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*❌ Broken Links:*\n{broken_text}"
            }
        })

    if cta_text:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚠️ Dead CTAs:*\n{cta_text}"
            }
        })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View Full Report →"
                },
                "url": f"https://brokenlinkchecker-olive.vercel.app?url={url}",
                "style": "primary"
            }
        ]
    })

    payload = {"blocks": blocks}

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url, 
                json=payload, 
                timeout=5.0
            )
    except Exception as e:
        print(f"[Slack] Failed: {e}")


def _calculate_health_score(results: list) -> int:
    total = len(results)
    if total == 0:
        return 100

    def get(r, field):
        return r.get(field) if isinstance(r, dict) else getattr(r, field, None)

    # HTTP-ok but unverifiable (e.g. a #section we could not confirm) is not
    # a working link — it must not inflate the numerator.
    ok = sum(
        1 for r in results
        if get(r, "label") == "ok" and (get(r, "bucket") or "ok") == "ok"
    )
    broken_penalty = sum(3 for r in results if get(r, "label") == "broken")
    # Only high/medium-confidence dead CTAs cost health. Low-confidence
    # candidates land in the "unverifiable" bucket and must not be scored as
    # defects — we cannot prove they are broken.
    dead_cta_penalty = sum(
        2 for r in results
        if get(r, "label") == "dead_cta" and get(r, "bucket") == "dead_cta"
    )
    timeout_penalty = sum(1 for r in results if get(r, "label") == "timeout")
    score = round((ok / total) * 100) - broken_penalty - dead_cta_penalty - timeout_penalty
    return max(0, min(100, score))


def calculate_business_impact(
    label: str,
    category: str,
    days_broken: int = 0,
) -> dict:
    score = 0

    # Zone weight
    zone_weights = {
        "CTA": 40,
        "Navigation": 30,
        "Header": 25,
        "Body text": 15,
        "Footer": 10,
        "Other": 5,
        "Dead CTA": 35,
    }
    score += zone_weights.get(category, 5)

    # How long broken
    if days_broken > 14:
        score += 30
    elif days_broken > 7:
        score += 20
    elif days_broken > 3:
        score += 15
    elif days_broken > 1:
        score += 10
    else:
        score += 5

    # Label weight
    if label == "broken":
        score += 30
    elif label == "dead_cta":
        score += 25
    elif label == "error":
        score += 20

    # Classify
    if score >= 80:
        return {
            "score": score,
            "level": "Critical",
            "color": "#f87171",
            "description": "Fix immediately \u2014 high traffic area",
        }
    elif score >= 55:
        return {
            "score": score,
            "level": "High",
            "color": "#fb923c",
            "description": "Fix this week",
        }
    elif score >= 30:
        return {
            "score": score,
            "level": "Medium",
            "color": "#fbbf24",
            "description": "Fix when convenient",
        }
    else:
        return {
            "score": score,
            "level": "Low",
            "color": "#94a3b8",
            "description": "Low priority",
        }


@app.get("/scan")
async def scan(
    url: str = Query(..., description="URL to scan"),
    email: str = Query(default="anonymous", description="User email for monitoring"),
):
    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Launching headless browser...', 'percent': 5})}\n\n"
            await asyncio.sleep(0.1)

            links, detected_builders = await scrape_links(url)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Found {len(links)} links. Checking each one...', 'percent': 30})}\n\n"
            await asyncio.sleep(0.1)

            results = []
            total = len(links)

            if total == 0:
                yield f"data: {json.dumps({'type': 'result', 'data': [], 'health_score': 100, 'detected_builders': detected_builders})}\n\n"
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

            # Calculate business impact for actionable links
            for r in results:
                if r.label in ["broken", "dead_cta", "error"]:
                    r.impact = calculate_business_impact(
                        label=r.label,
                        category=r.category,
                        days_broken=0,
                    )

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

            await send_slack_notification(url, health_score, results)

            # "14 unique links across 47 placements" — the same URL linked from
            # nav and footer is fetched once but counted in both places.
            total_placements = sum(getattr(r, "occurrences", 1) or 1 for r in results)

            yield f"data: {json.dumps({'type': 'result', 'data': [r.dict() for r in results], 'health_score': health_score, 'detected_builders': detected_builders, 'total_links': len(results), 'total_placements': total_placements})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/scan-site")
async def scan_site(
    url: str = Query(..., description="Base site URL to scan, e.g. https://example.com"),
    email: str = Query(default="anonymous"),
    max_pages: int = Query(default=50, le=200),
):
    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Discovering pages via sitemap or crawl...', 'percent': 5})}\n\n"
            await asyncio.sleep(0.1)

            discovered_pages = await discover_site_urls(url, max_pages)
            if not discovered_pages:
                yield f"data: {json.dumps({'type': 'progress', 'message': 'No pages discovered. Scraping homepage...', 'percent': 10})}\n\n"
                discovered_pages = [url]

            total_pages = len(discovered_pages)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Discovered {total_pages} pages. Starting scan...', 'percent': 15})}\n\n"
            await asyncio.sleep(0.1)

            sem = asyncio.Semaphore(5)
            queue = asyncio.Queue()
            completed_pages = 0
            all_results = []
            # Builders seen anywhere on the site, in first-seen order.
            site_builders: list[str] = []

            async def scan_page_worker(page_url: str):
                nonlocal completed_pages
                async with sem:
                    # Emit status update: starting scan
                    from urllib.parse import urlparse
                    path_to_show = urlparse(page_url).path or "/"
                    await queue.put({
                        "type": "progress",
                        "message": f"Scanning page {completed_pages + 1}/{total_pages}: {path_to_show}"
                    })
                    try:
                        links, page_builders = await scrape_links(page_url)
                        for b in page_builders:
                            if b not in site_builders:
                                site_builders.append(b)
                        page_results = []
                        if links:
                            async for i, res in check_all_links(links):
                                page_results.append(res)

                            actionable_count = sum(1 for r in page_results if r.label in ["broken", "dead_cta", "blocked"])
                            if actionable_count > 0:
                                page_results = await process_suggestions(page_results)

                        # Convert and enrich
                        serialized = []
                        for r in page_results:
                            rd = r.dict()
                            rd["found_on_page"] = page_url
                            if r.label in ["broken", "dead_cta", "error"]:
                                rd["impact"] = calculate_business_impact(
                                    label=r.label,
                                    category=r.category,
                                    days_broken=0,
                                )
                            serialized.append(rd)

                        completed_pages += 1
                        pct = 15 + int((completed_pages / total_pages) * 75)
                        await queue.put({
                            "type": "progress",
                            "message": f"Scanned page {completed_pages}/{total_pages}: {path_to_show}",
                            "percent": pct
                        })
                        await queue.put({"type": "data", "results": serialized})
                    except Exception as page_err:
                        print(f"[ScanSite] Error scanning page {page_url}: {page_err}")
                        completed_pages += 1
                        pct = 15 + int((completed_pages / total_pages) * 75)
                        await queue.put({
                            "type": "progress",
                            "message": f"Failed page {completed_pages}/{total_pages}: {path_to_show}",
                            "percent": pct
                        })

            # Launch all workers
            tasks = [asyncio.create_task(scan_page_worker(p)) for p in discovered_pages]

            # Read from the queue and stream progress/data
            from urllib.parse import urlparse
            while completed_pages < total_pages or not queue.empty():
                try:
                    # Non-blocking check to retrieve queued events
                    msg = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if msg["type"] == "progress":
                        yield f"data: {json.dumps({'type': 'progress', 'message': msg['message'], 'percent': msg.get('percent', 15)})}\n\n"
                    elif msg["type"] == "data":
                        all_results.extend(msg["results"])
                except asyncio.TimeoutError:
                    if completed_pages >= total_pages and queue.empty():
                        break
                    await asyncio.sleep(0.05)

            # Ensure all workers are joined
            await asyncio.gather(*tasks, return_exceptions=True)

            # Deduplicate results at target URL level
            # Store all found_on_pages
            deduped = {}
            for r in all_results:
                r_url = r["url"]
                found_page = r.get("found_on_page") or url
                
                # Normalize path for readability in found_on_pages
                parsed_found = urlparse(found_page)
                page_path = parsed_found.path or "/"
                if parsed_found.query:
                    page_path += f"?{parsed_found.query}"

                if r_url not in deduped:
                    r["found_on_pages"] = [page_path]
                    deduped[r_url] = r
                else:
                    if page_path not in deduped[r_url]["found_on_pages"]:
                        deduped[r_url]["found_on_pages"].append(page_path)

            final_results = list(deduped.values())
            health_score = _calculate_health_score(final_results)

            # Save full site scan to Supabase (non-blocking)
            try:
                await save_scan(
                    site_url=url,
                    user_email=email,
                    results=final_results,
                    health_score=health_score,
                    pages_scanned=total_pages,
                )
            except Exception as db_err:
                print(f"[DB] Save site scan failed (non-critical): {db_err}")

            # Send Slack notification
            class SimpleNamespace:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
            slack_results = [SimpleNamespace(**r) for r in final_results]
            await send_slack_notification(url, health_score, slack_results)

            # Yield final result event
            total_placements = sum(r.get("occurrences", 1) or 1 for r in final_results)

            yield f"data: {json.dumps({'type': 'result', 'data': final_results, 'health_score': health_score, 'pages_scanned': total_pages, 'detected_builders': site_builders, 'total_links': len(final_results), 'total_placements': total_placements})}\n\n"

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


@app.post("/register")
async def register(
    url: str = Query(..., description="Site URL to track"),
    email: str = Query(..., description="User email"),
):
    """Register a site for tracking."""
    from database import _get_client
    import asyncio as _asyncio

    def _register():
        client = _get_client()
        client.table("sites").upsert({
            "url": url,
            "user_email": email,
        }, on_conflict="url,user_email").execute()
        return {"registered": True}

    try:
        result = await _asyncio.to_thread(_register)
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/uptime")
async def uptime(url: str = Query(...)):
    try:
        from database import get_uptime
        data = await get_uptime(url)
        return {"url": url, "issues": data}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/dashboard")
async def dashboard_data():
    import asyncio as _asyncio

    def _get_dashboard():
        from database import _get_client
        client = _get_client()

        # Get all sites with their latest scan
        sites = client.table("sites")\
            .select("*, scans(id, scanned_at, total_links, broken_count, dead_cta_count, health_score)")\
            .order("last_scanned_at", desc=True)\
            .execute()

        return sites.data

    try:
        data = await _asyncio.to_thread(_get_dashboard)
        return {"sites": data}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/sites")
async def add_site_endpoint(site: SiteCreate):
    try:
        from database import add_site
        await add_site(site.url, site.name, site.client, site.freq, site.user_email)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/sites/{site_id}")
async def delete_site_endpoint(site_id: str):
    try:
        from database import delete_site
        await delete_site(site_id)
        return {"status": "success"}
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