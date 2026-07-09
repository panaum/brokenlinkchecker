import httpx
import asyncio
import re
import time
import random
from urllib.parse import urlparse, unquote
from models import RawLink, LinkResult
from redirect_rules import FLAG_LOOP, MAX_REDIRECT_HOPS, analyze_chain
from resources import describe_resource_failure
from typing import AsyncIterator, Optional

SEMAPHORE = asyncio.Semaphore(20)
TIMEOUT = httpx.Timeout(10.0)

# A page can link hundreds of URLs on one host. Firing 20 of them at a single
# domain gets the connections reset by its WAF, which then looks like broken
# links. Cap in-flight requests per domain; the global semaphore still bounds
# total concurrency across domains.
DOMAIN_CONCURRENCY = 4

MAX_ATTEMPTS = 3

# When a domain starts throwing connections, slow down instead of writing off
# its links as unverifiable. Each transport failure adds a delay for that
# domain; each success decays it.
PENALTY_STEP = 0.75
PENALTY_MAX = 4.0

# Per-domain last-request timestamps for rate-limiting delay
_domain_last_request: dict[str, float] = {}
_domain_locks: dict[str, asyncio.Lock] = {}
_domain_semaphores: dict[str, asyncio.Semaphore] = {}
_domain_penalty: dict[str, float] = {}


def _domain_semaphore(domain: str) -> asyncio.Semaphore:
    if domain not in _domain_semaphores:
        _domain_semaphores[domain] = asyncio.Semaphore(DOMAIN_CONCURRENCY)
    return _domain_semaphores[domain]


def _penalize(domain: str) -> None:
    _domain_penalty[domain] = min(PENALTY_MAX, _domain_penalty.get(domain, 0.0) + PENALTY_STEP)


def _reward(domain: str) -> None:
    current = _domain_penalty.get(domain, 0.0)
    if current:
        _domain_penalty[domain] = current / 2 if current > 0.1 else 0.0

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


# ─── Transport failures ─────────────────────────────────────────────────────
# No transport error proves a link is broken on its own. Checking hundreds of
# links makes servers reset connections and overloads the OS resolver, so a
# perfectly healthy host raises ConnectError("getaddrinfo failed"). A WAF can
# RST a connection just as easily. The single provable case is a hostname that
# still fails to resolve when we ask the resolver directly, on its own — that
# is a dead domain. Everything else is "unverifiable".
_DNS_FAILURE_MARKERS = (
    "name or service not known",
    "nodename nor servname",
    "getaddrinfo failed",
    "temporary failure in name resolution",
    "no address associated with hostname",
    "name does not resolve",
    "11001",           # WSAHOST_NOT_FOUND
)


def is_dns_failure(exc: Exception) -> bool:
    if not isinstance(exc, httpx.ConnectError):
        return False
    return any(m in str(exc).lower() for m in _DNS_FAILURE_MARKERS)


def classify_exception(exc: Exception) -> tuple:
    """(label, bucket) for a transport failure, before DNS is confirmed."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", "unverifiable"
    if is_dns_failure(exc):
        # Provisional: only a direct resolver check can confirm it.
        return "error", "broken"
    # Reset, refused, protocol error, SSL, proxy, pool exhaustion — under a
    # rate-limited crawl these are indistinguishable from throttling.
    return "error", "unverifiable"


async def hostname_resolves(host: str) -> bool:
    """Ask the resolver directly, with one retry. A hostname that resolves here
    means the earlier failure was resolver overload, not a dead domain."""
    if not host:
        return False
    loop = asyncio.get_running_loop()
    for attempt in range(2):
        try:
            await loop.getaddrinfo(host, None)
            return True
        except Exception:
            if attempt == 0:
                await asyncio.sleep(0.5)
    return False


# ─── mailto: / tel: validation (never fetched, only syntax-checked) ──────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def validate_contact(url: str) -> tuple:
    """(ok, reason) for a mailto:/tel:/sms: href."""
    scheme, _, rest = url.partition(":")
    scheme = scheme.lower()
    target = rest.split("?", 1)[0].strip()   # drop ?subject=/&body=
    target = unquote(target)

    if not target:
        return False, f"{scheme}: link has no recipient"

    if scheme == "mailto":
        # A mailto: may carry several comma-separated recipients.
        addresses = [a.strip() for a in target.split(",") if a.strip()]
        if not addresses:
            return False, "mailto: link has no address"
        bad = [a for a in addresses if not _EMAIL_RE.match(a)]
        if bad:
            return False, f"Malformed email address: {bad[0]}"
        return True, ""

    # tel:/sms: — digits, optional leading +, separators allowed.
    if not re.fullmatch(r"\+?[0-9()\-.\s]+", target):
        return False, f"Malformed phone number: {target}"
    if len(re.sub(r"\D", "", target)) < 7:
        return False, f"Phone number too short to dial: {target}"
    return True, ""


# ─── Cross-page fragment validation ─────────────────────────────────────────
# A link like /about-us/#team returns 200 whether or not #team exists — HTTP
# never sees the fragment. Without this check the visitor silently lands at the
# top of the page and the tool reports "ok".
_SPA_BODY_MARKERS = (
    "data-reactroot", "__next_data__", "__nuxt", "ng-version",
    "data-v-app", "data-svelte", "q:container",
)

# An element id, as opposed to client-side state smuggled through the fragment:
#   validator.schema.org/#url=http%3A%2F%2Fwebflow.com   (query params)
#   /app#!/dashboard  ·  /docs#/getting-started          (hash routing)
# Those never name an element, so validating them is meaningless.
_IDENTIFIER_FRAGMENT_RE = re.compile(r"^[A-Za-z0-9_\-.:]+$")


def is_identifier_fragment(fragment: str) -> bool:
    return bool(_IDENTIFIER_FRAGMENT_RE.match(fragment))


def _fragment_present(body: str, fragment: str) -> bool:
    frag = re.escape(fragment)
    pattern = rf"""(?:id|name)\s*=\s*(?:"{frag}"|'{frag}'|{frag}(?=[\s/>]))"""
    return re.search(pattern, body, re.IGNORECASE) is not None


def _target_is_js_rendered(body: str) -> bool:
    """We fetch without JS. If the target looks like an SPA, a missing id proves
    nothing — the framework may inject it on hydration."""
    head = body[:4000].lower()
    return any(m in head for m in _SPA_BODY_MARKERS)


def build_redirect_chain(response: httpx.Response) -> list:
    """[{url, status}, …] across every hop, ending at the final response.

    httpx exposes the redirects it followed in `response.history`.
    """
    chain = [{"url": str(hop.url), "status": hop.status_code} for hop in response.history]
    chain.append({"url": str(response.url), "status": response.status_code})
    return chain if len(chain) > 1 else []


def _fragment_absence_is_provable(body: str) -> bool:
    """Only a page that runs no JavaScript can prove an id is truly absent.

    Anything with a <script> may build the target at runtime — webflow.com's
    /discover/popular#recent is a JS-rendered tab that is nowhere in the static
    HTML. Calling that "broken" is a false alarm, so it degrades to unverifiable.
    """
    if _target_is_js_rendered(body):
        return False
    return "<script" not in body.lower()


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
        min_gap = random.uniform(0.1, 0.5) + _domain_penalty.get(domain, 0.0)
        if gap < min_gap:
            await asyncio.sleep(min_gap - gap)
        _domain_last_request[domain] = time.monotonic()


async def check_single(client: httpx.AsyncClient, link: RawLink) -> LinkResult:
    def _result(label: str, bucket: Optional[str] = None, **kwargs) -> LinkResult:
        """Build a LinkResult, overriding the RawLink's placeholder bucket."""
        fields = link.dict()
        fields["bucket"] = bucket or bucket_for_label(label)
        # Priority triages *flagged* items. A working link has nothing to
        # triage, so it carries no priority and the UI renders no chip.
        if fields["bucket"] == "ok":
            fields["priority"] = None
        elif fields["bucket"] == "broken" and not fields.get("reason"):
            resource_type = fields.get("resource_type") or "anchor"
            if resource_type != "anchor":
                # "Broken <script src> — breaks page behaviour". A 404 script
                # leaves the page returning 200 while nothing on it works.
                fields["reason"] = describe_resource_failure(resource_type)
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

    if link.link_kind == "contact":
        ok, reason = validate_contact(link.url)
        return _result(
            "ok" if ok else "broken",
            status_code=None,
            final_url=None,
            response_ms=0,
            error=None if ok else reason,
        )

    if link.link_kind == "anchor":
        # The scraper only emits anchors whose target exists in the rendered
        # DOM; unresolved ones go through the dead-CTA detector instead.
        return _result("ok", status_code=None, final_url=None, response_ms=0)

    domain = urlparse(link.url).netloc

    async with SEMAPHORE, _domain_semaphore(domain):
        await _domain_delay(domain)

        for attempt in range(MAX_ATTEMPTS):
            last_attempt = attempt == MAX_ATTEMPTS - 1
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
                _reward(domain)

                # Redirect forensics. Informational: a redirect is not a failure,
                # so this never changes the label or the bucket.
                chain = build_redirect_chain(r)
                redirect_meta = {
                    "redirect_chain": chain,
                    "redirect_flags": analyze_chain(chain),
                }

                # Detect bot-blocking independent of status code
                if r.status_code == 403 or _is_bot_blocked(r):
                    return _result(
                        "blocked",
                        status_code=r.status_code,
                        final_url=str(r.url) if str(r.url) != link.url else None,
                        response_ms=elapsed,
                        error="Could not verify — server blocked automated request",
                        **redirect_meta,
                    )

                label = classify(r.status_code)
                final_url = str(r.url) if str(r.url) != link.url else None

                # /about-us/#team returns 200 regardless of whether #team
                # exists. Validate the fragment against the body we just
                # downloaded — no extra request.
                if label == "ok" and link.fragment and is_identifier_fragment(link.fragment):
                    try:
                        body = r.text[:500000]
                    except Exception:
                        body = ""
                    # Only judge something that is actually an HTML document —
                    # a 200 challenge/interstitial page has no ids either.
                    if "<html" not in body.lower():
                        body = ""
                    if body and not _fragment_present(body, link.fragment):
                        target_page = link.url.split("#", 1)[0]
                        if _fragment_absence_is_provable(body):
                            result = _result(
                                "dead_cta",
                                status_code=r.status_code,
                                final_url=final_url,
                                response_ms=elapsed,
                                error=(
                                    f"Section #{link.fragment} not found on {target_page} — "
                                    "the visitor lands at the top of the page"
                                ),
                                **redirect_meta,
                            )
                            result.reason = (
                                f"Link points at #{link.fragment}, which does not exist on "
                                f"{target_page}"
                            )
                            return result

                        # The target may build the section with JavaScript, so a
                        # missing id proves nothing. Soft warning, never red.
                        # Pass the bucket up front: it is a flagged item, so it
                        # must keep its priority.
                        result = _result(
                            "ok",
                            bucket="unverifiable",
                            status_code=r.status_code,
                            final_url=final_url,
                            response_ms=elapsed,
                            error=(
                                f"Couldn't confirm section #{link.fragment} on {target_page} — "
                                "it may be rendered by JavaScript. Please check manually."
                            ),
                            **redirect_meta,
                        )
                        result.confidence = "low"
                        result.reason = (
                            f"Section #{link.fragment} is not in the HTML of {target_page}; "
                            "it may be added at runtime"
                        )
                        return result

                return _result(
                    label,
                    status_code=r.status_code,
                    final_url=final_url,
                    response_ms=elapsed,
                    **redirect_meta,
                )
            except httpx.TooManyRedirects:
                # Deterministic: retrying walks the same circle. A loop is not a
                # broken link — we simply never reached a destination.
                return _result(
                    "redirect",
                    bucket="unverifiable",
                    status_code=None,
                    final_url=None,
                    response_ms=int((time.monotonic() - start) * 1000),
                    error=(
                        f"Redirect loop — stopped after {MAX_REDIRECT_HOPS} hops. "
                        "The link never reaches a destination."
                    ),
                    redirect_flags=[FLAG_LOOP],
                )
            except httpx.TimeoutException:
                _penalize(domain)
                if not last_attempt:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                elapsed = int((time.monotonic() - start) * 1000)
                return _result(
                    "timeout",
                    status_code=None,
                    final_url=None,
                    response_ms=elapsed,
                )
            except Exception as e:
                _penalize(domain)
                if not last_attempt:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                label, bucket = classify_exception(e)

                # A DNS error under a heavy crawl is usually resolver overload.
                # Confirm against the resolver before calling the link broken.
                if bucket == "broken" and is_dns_failure(e):
                    if await hostname_resolves(domain):
                        bucket = "unverifiable"

                if bucket == "broken":
                    error = f"Domain does not resolve — {domain} appears to be dead"
                else:
                    error = (
                        f"Could not reach the server ({type(e).__name__}) — it may be "
                        f"rate-limiting automated requests. Please check manually."
                    )
                return _result(
                    label,
                    bucket=bucket,
                    status_code=None,
                    final_url=None,
                    response_ms=0,
                    error=error,
                )

        return _result(
            "error",
            bucket="unverifiable",
            status_code=None,
            final_url=None,
            response_ms=0,
            error="Max retries exceeded",
        )


async def check_all_links(links: list[RawLink]) -> AsyncIterator[tuple[int, LinkResult]]:
    async with httpx.AsyncClient(
        follow_redirects=True,
        verify=False,
        # Stop walking a redirect circle. httpx raises TooManyRedirects, which
        # check_single reports as an (unverifiable) loop rather than a failure.
        max_redirects=MAX_REDIRECT_HOPS,
    ) as client:
        tasks = [check_single(client, link) for link in links]
        for i, coro in enumerate(asyncio.as_completed(tasks), start=1):
            result = await coro
            yield i, result