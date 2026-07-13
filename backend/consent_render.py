"""Multi-state consent renders — the NEW capture (existing pipeline only stored
detected integrations, not per-request timing under consent states).

Each mode loads the page fresh and records EVERY third-party request with its
consent class + timing. Modes: cold (no interaction), reject/accept (operate the
CMP), gpc (US signal, no interaction), optout (locate the opt-out mechanism).

The engine that JUDGES these captures (consent_verdict) is deterministic and
unit-tested; this module is the browser I/O that feeds it. It fails safe: an
undetected/inoperable CMP is reported as such, never guessed.
"""
from urllib.parse import urlparse

from consent_classify import consent_class
from consent_cmp import CMP_ADAPTERS, adapter_for, _REJECT_TEXT, _ACCEPT_TEXT
from consent_verdict import ENGINE_VERSION
from consent_classify import CLASSIFICATION_VERSION


def _host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _third_party(url, site_host):
    h = _host(url)
    sh = (site_host or "").replace("www.", "")
    return bool(h) and not (h == sh or h.endswith("." + sh)) and url.startswith(("http://", "https://"))


async def _capture_page(context, url, site_host):
    """Open a page, log every third-party request with class + timing, load,
    settle, and return (page, requests). Caller closes the page."""
    import time
    page = await context.new_page()
    requests = []
    t0 = time.monotonic()

    def on_request(req):
        u = req.url
        if not _third_party(u, site_host):
            return
        h = _host(u)
        cc = consent_class(h, u, site_host)
        requests.append({"host": h, "url": u[:400], "class": cc["class"],
                         "provenance": cc["provenance"], "category": cc["category"],
                         "resource_type": req.resource_type,
                         "ms_after_load": int((time.monotonic() - t0) * 1000)})

    page.on("request", on_request)
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
    except Exception:
        pass
    return page, requests


async def cold_render(context, url, site_host):
    """Load, interact with nothing. Every captured request is pre-consent."""
    from consent_cmp import detect_cmp_in_html
    page, requests = await _capture_page(context, url, site_host)
    try:
        html = await page.content()
    except Exception:
        html = ""
    vendor = detect_cmp_in_html(html)
    for r in requests:
        r["pre_consent_ui"] = True
    await page.close()
    return {"mode": "cold", "requests": requests,
            "cmp": {"detected": vendor is not None, "vendor": vendor}}


async def _operate(page, selectors):
    """Click the first matching selector. Returns click-depth (1 if top-level
    control, 2 if we had to open a preferences panel first) or None."""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=3000)
                await page.wait_for_timeout(1200)
                return 1
        except Exception:
            continue
    return None


async def _operate_cmp(context, url, site_host, which):
    """which ∈ {'reject','accept'}. Detect the CMP, operate it, capture what
    fires after. Returns the session dict with cmp operability recorded."""
    from consent_cmp import detect_cmp_in_html
    page, _pre = await _capture_page(context, url, site_host)
    try:
        html = await page.content()
    except Exception:
        html = ""
    vendor = detect_cmp_in_html(html)
    result = {"mode": which, "cmp": {"detected": vendor is not None, "vendor": vendor, "operated": False}}
    post = []

    def on_post(req):
        u = req.url
        if _third_party(u, site_host):
            h = _host(u)
            cc = consent_class(h, u, site_host)
            post.append({"host": h, "url": u[:400], "class": cc["class"],
                         "provenance": cc["provenance"], "category": cc["category"]})

    adapter = adapter_for(vendor) if vendor and vendor != "generic" else None
    selectors = (adapter[which] if adapter else _generic_selectors(which))
    page.on("request", on_post)
    depth = await _operate(page, selectors)
    if depth is not None:
        result["cmp"]["operated"] = True
        result["cmp"][f"{which}_clicks"] = depth
    await page.wait_for_timeout(1500)
    result["requests"] = post
    await page.close()
    return result


def _generic_selectors(which):
    words = "reject|decline|refuse|only necessary|deny" if which == "reject" else "accept all|accept|allow all|agree"
    return [f"button:has-text('{w}')" for w in words.split("|")] + \
           [f"a:has-text('{w}')" for w in words.split("|")]


async def reject_render(context, url, site_host):
    return await _operate_cmp(context, url, site_host, "reject")


async def accept_render(context, url, site_host):
    return await _operate_cmp(context, url, site_host, "accept")


async def gpc_render(browser, url, site_host):
    """US regime: load with Sec-GPC:1 + navigator.globalPrivacyControl=true, no
    interaction. Needs its own context to set the header + init script."""
    context = await browser.new_context(extra_http_headers={"Sec-GPC": "1"})
    await context.add_init_script("Object.defineProperty(navigator,'globalPrivacyControl',{get:()=>true});")
    try:
        page, requests = await _capture_page(context, url, site_host)
        await page.close()
    finally:
        await context.close()
    return {"mode": "gpc", "requests": requests, "cmp": {}}


_OPTOUT_TEXT = _REJECT_TEXT  # reuse; opt-out links share decline-ish wording
_DNS_PATTERNS = ("do not sell", "do not sell or share", "do not share", "your privacy choices",
                 "opt out", "opt-out", "privacy choices", "ccpa", "cpra")


async def optout_check(context, url, site_host):
    """US: locate a 'Do Not Sell or Share'-class link in the rendered DOM, verify
    it resolves and that its destination has a form/CMP mechanism (reuses the
    form-audit idea). Operating it end-to-end is a v2 note."""
    import httpx
    page, _ = await _capture_page(context, url, site_host)
    href = None
    try:
        links = await page.query_selector_all("a")
        for a in links:
            txt = ((await a.inner_text()) or "").strip().lower()
            if any(p in txt for p in _DNS_PATTERNS):
                href = await a.get_attribute("href")
                if href:
                    break
    except Exception:
        pass
    await page.close()
    if not href:
        return {"mode": "optout", "optout": {"found": False}, "requests": []}
    dest = href if href.startswith("http") else _join(url, href)
    resolves = False
    mechanism = False
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as c:
            r = await c.get(dest)
            resolves = r.status_code < 400
            body = r.text.lower()
            mechanism = ("<form" in body or any(m for m in ("onetrust", "cookiebot", "privacy",
                          "opt-out", "do not sell") if m in body))
    except Exception:
        resolves = False
    return {"mode": "optout",
            "optout": {"found": True, "resolves": resolves, "mechanism_present": mechanism, "url": dest},
            "requests": []}


def _join(base, href):
    from urllib.parse import urljoin
    return urljoin(base, href)


async def run_consent_session(site_id, page_url, regime):
    """Run all applicable modes for a regime and build the ledger rows (one per
    mode) with verdicts + version stamps. Returns list of session dicts to
    persist. Never mutates anything."""
    from playwright.async_api import async_playwright
    from consent_verdict import uk_verdicts, us_verdicts

    site_host = _host(page_url)
    sessions = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            if regime in ("UK", "BOTH"):
                ctx = await browser.new_context()
                cold = await cold_render(ctx, page_url, site_host)
                rej = await reject_render(ctx, page_url, site_host)
                acc = await accept_render(ctx, page_url, site_host)
                await ctx.close()
                cmp = {**cold["cmp"], **rej["cmp"],
                       "accept_clicks": acc["cmp"].get("accept_clicks"),
                       "reject_clicks": rej["cmp"].get("reject_clicks")}
                verdicts = uk_verdicts(cold["requests"], rej.get("requests", []), cmp)
                for mode_data in (cold, rej, acc):
                    sessions.append(_row(site_id, page_url, "UK", mode_data,
                                         verdicts if mode_data["mode"] == "cold" else []))
            if regime in ("US", "BOTH"):
                gpc = await gpc_render(browser, page_url, site_host)
                ctx2 = await browser.new_context()
                oc = await optout_check(ctx2, page_url, site_host)
                await ctx2.close()
                verdicts = us_verdicts(gpc["requests"], oc.get("optout", {}))
                sessions.append(_row(site_id, page_url, "US", gpc, verdicts))
                sessions.append(_row(site_id, page_url, "US", oc, []))
        finally:
            await browser.close()
    return sessions


def _row(site_id, page_url, regime, mode_data, verdicts):
    return {"site_id": site_id, "page_url": page_url, "regime": regime,
            "mode": mode_data["mode"], "requests": mode_data.get("requests", []),
            "cmp": mode_data.get("cmp", {}), "optout": mode_data.get("optout", {}),
            "verdicts": verdicts, "screenshots": [],
            "engine_version": ENGINE_VERSION, "classification_version": CLASSIFICATION_VERSION}
