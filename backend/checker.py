import httpx
import asyncio
import time
from models import RawLink, LinkResult
from typing import AsyncIterator


SEMAPHORE = asyncio.Semaphore(20)  # max 20 concurrent requests
TIMEOUT = httpx.Timeout(8.0)


def classify(status: int | None) -> str:
    if status is None:
        return "timeout"
    if 200 <= status < 300:
        return "ok"
    if 300 <= status < 400:
        return "redirect"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "broken"
    if status >= 400:
        return "broken"
    return "unknown"


async def check_single(client: httpx.AsyncClient, link: RawLink) -> LinkResult:
    # Dead CTAs have no real URL to check — return immediately
    if link.category == "Dead CTA":
        return LinkResult(
            **link.model_dump(),
            status_code=None,
            label="dead_cta",
            final_url=None,
            response_ms=0,
            error="No href or placeholder link",
        )
    async with SEMAPHORE:
        start = time.monotonic()
        try:
            # Try HEAD first (lightweight), fall back to GET
            r = await client.head(link.url, timeout=TIMEOUT, follow_redirects=True)
            if r.status_code == 405:
                r = await client.get(
                    link.url, timeout=TIMEOUT, follow_redirects=True
                )
            elapsed = int((time.monotonic() - start) * 1000)
            return LinkResult(
                **link.model_dump(),
                status_code=r.status_code,
                label=classify(r.status_code),
                final_url=str(r.url) if str(r.url) != link.url else None,
                response_ms=elapsed,
            )
        except httpx.TimeoutException:
            elapsed = int((time.monotonic() - start) * 1000)
            return LinkResult(
                **link.model_dump(),
                status_code=None,
                label="timeout",
                final_url=None,
                response_ms=elapsed,
            )
        except Exception as e:
            return LinkResult(
                **link.model_dump(),
                status_code=None,
                label="error",
                final_url=None,
                response_ms=0,
                error=str(e),
            )


async def check_all_links(
    links: list[RawLink],
) -> AsyncIterator[tuple[int, LinkResult]]:
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; LinkCheckerBot/1.0)"},
        follow_redirects=True,
        verify=False,  # avoids SSL cert errors on broken sites
    ) as client:
        tasks = [check_single(client, link) for link in links]
        for i, coro in enumerate(asyncio.as_completed(tasks), start=1):
            result = await coro
            yield i, result
