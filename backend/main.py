import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from scraper import scrape_links
from checker import check_all_links
import json

app = FastAPI(title="Broken Link Checker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-production-domain.com",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/scan")
async def scan(url: str = Query(..., description="URL to scan")):
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
                yield f"data: {json.dumps({'type': 'result', 'data': []})}\n\n"
                return

            async for i, result in check_all_links(links):
                results.append(result)
                pct = 30 + int((i / total) * 65)
                yield f"data: {json.dumps({'type': 'progress', 'message': f'Checked {i}/{total} links...', 'percent': pct})}\n\n"

            yield f"data: {json.dumps({'type': 'result', 'data': [r.model_dump() for r in results]})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return {"status": "ok"}