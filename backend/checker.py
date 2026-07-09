import httpx
import asyncio
import time
import random
from urllib.parse import urlparse
from models import RawLink, LinkResult
from typing import AsyncIterator, Optional

SEMAPHORE = asyncio.Semaphore(20)
TIMEOUT = httpx.Timeout(10.0)

# Per-domain last-request timestamps for rate-limiting delay
_domain_last_request: dict[str, float] = {}
_domain_locks: dict[str, asyncio.Lock] = {}

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Precise challenge-page phrases only — generic words like "robot"/"automated"/
# "captcha" match ordinary marketing copy and <meta name="robots">, mislabeling
# healthy 200 pages as blocked.
_BOT_BLOCK_PHRASES = (
    "just a moment",
    "attention required",
    "verify you are human",
    "verifying you are human",
    "enable javascript and cookies to continue",
    "access denied",
    "ddos-guard",
    "px-captcha",
    "request unsuccessful. incapsula",
)

# Statuses where sniffing the body for a challenge page is meaningful. A 200 with
# marketing copy must never be treated as blocked.
_SNIFF_STATUSES = {401, 403, 405, 406, 409, 429, 503}


def _browser_headers(url: str) -> dict[str, str]:
    """Return a realistic browser header set with the Referer set to the origin of url."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "User-Agent": _CHROME_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": origin,
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }


def _is_bot_blocked(response: httpx.Response) -> bool:
    """Detect Cloudflare / WAF bot-blocking from headers or body snippet."""
    # Header markers are authoritative regardless of status code.
    if "cf-mitigated" in response.headers:
        return True
    server = response.headers.get("server", "").lower()
    if "cloudflare" in server and response.status_code in (403, 503):
        return True
    # Only sniff the body for challenge phrases on statuses that plausibly
    # indicate blocking — never on a healthy 200.
    if response.status_code not in _SNIFF_STATUSES:
        return False
    try:
        body_snip = response.text[:2000].lower()
        return any(phrase in body_snip for phrase in _BOT_BLOCK_PHRASES)
    except Exception:
        return False


# Three-bucket taxonomy. "broken" is a provable failure; "unverifiable" is an
# honest "can't judge from here". Anything we are not sure about lands in
# "unverifiable" — for a client-facing QA tool a false alarm is worse than a
# soft warning. "ok" is the sentinel for healthy links, which belong to no
# issue bucket at all.
_LABEL_BUCKETS = {
    "ok": "ok",
    "redirect": "ok",
    "broken": "broken",     # 404 / 410 / other 4xx
    "error": "broken",      # 5xx, DNS failure, connection refused
    "blocked": "unverifiable",   # 401/403/405/429/999, bot-blocked
    "timeout": "unverifiable",
    "dead_cta": "dead_cta",
}


def bucket_for_label(label: str) -> str:
    return _LABEL_BUCKETS.get(label, "unverifiable")


def classify(status: Optional[int]) -> str:
    if status is None:          return "timeout"
    if 200 <= status < 300:     return "ok"
    if 300 <= status < 400:     return "redirect"
    if status == 401:           return "blocked"   # auth required — not truly broken
    if status == 403:           return "blocked"   # forbidden — not truly broken
    if status == 405:           return "blocked"   # method not allowed — anti-bot
    if status == 404:           return "broken"
    if status == 410:           return "broken"
    if status == 429:           return "blocked"   # rate limited — not truly broken
    if status == 999:           return "blocked"   # LinkedIn anti-bot status
    if 500 <= status < 600:     return "error"
    if status >= 400:           return "broken"
    return "unknown"


async def _domain_delay(domain: str) -> None:
    """Enforce a small random delay between requests to the same domain."""
    if domain not in _domain_locks:
        _domain_locks[domain] = asyncio.Lock()

    async with _domain_locks[domain]:
        now = time.monotonic()
        last = _domain_last_request.get(domain, 0.0)
        gap = now - last
        min_gap = random.uniform(0.1, 0.5)
        if gap < min_gap:
            await asyncio.sleep(min_gap - gap)
        _domain_last_request[domain] = time.monotonic()


async def check_single(client: httpx.AsyncClient, link: RawLink) -> LinkResult:
    def _result(label: str, **kwargs) -> LinkResult:
        """Build a LinkResult, overriding the RawLink's placeholder bucket."""
        fields = link.dict()
        fields["bucket"] = bucket_for_label(label)
        return LinkResult(**fields, label=label, **kwargs)

    if link.category == "Dead CTA":
        # The detector already assigned dead_cta vs unverifiable from its own
        # confidence; preserve that rather than deriving it from the label.
        return LinkResult(
            **link.dict(),
            status_code=None,
            label="dead_cta",
            final_url=None,
            response_ms=0,
            error="No href or placeholder link",
        )

    domain = urlparse(link.url).netloc

    async with SEMAPHORE:
        await _domain_delay(domain)

        for attempt in range(2):
            start = time.monotonic()
            try:
                headers = _browser_headers(link.url)
                r = await client.get(
                    link.url,
                    headers=headers,
                    timeout=TIMEOUT,
                    follow_redirects=True,
                )
                elapsed = int((time.monotonic() - start) * 1000)

                # Detect bot-blocking independent of status code
                if r.status_code == 403 or _is_bot_blocked(r):
                    return _result(
                        "blocked",
                        status_code=r.status_code,
                        final_url=str(r.url) if str(r.url) != link.url else None,
                        response_ms=elapsed,
                        error="Could not verify — server blocked automated request",
                    )

                return _result(
                    classify(r.status_code),
                    status_code=r.status_code,
                    final_url=str(r.url) if str(r.url) != link.url else None,
                    response_ms=elapsed,
                )
            except httpx.TimeoutException:
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                elapsed = int((time.monotonic() - start) * 1000)
                return _result(
                    "timeout",
                    status_code=None,
                    final_url=None,
                    response_ms=elapsed,
                )
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return _result(
                    "error",
                    status_code=None,
                    final_url=None,
                    response_ms=0,
                    error=str(e),
                )

        return _result(
            "error",
            status_code=None,
            final_url=None,
            response_ms=0,
            error="Max retries exceeded",
        )


async def check_all_links(links: list[RawLink]) -> AsyncIterator[tuple[int, LinkResult]]:
    async with httpx.AsyncClient(
        follow_redirects=True,
        verify=False,
    ) as client:
        tasks = [check_single(client, link) for link in links]
        for i, coro in enumerate(asyncio.as_completed(tasks), start=1):
            result = await coro
            yield i, result