from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from models import RawLink
from dead_cta_detector import (
    LISTENER_PROBE_JS,
    detect_builders,
    find_dead_ctas,
    fragment_targets,
    is_functional_fragment,
)
from resources import collect_resources, resources_from_stylesheets

# Priority mapping based on page zone
ZONE_PRIORITY = {
    "Navigation": "critical",
    "Header": "critical",
    "CTA": "high",
    "Hero": "high",
    "Body text": "medium",
    "Footer": "medium",
    "Other": "low",
    "Dead CTA": "medium",
}

ZONE_SELECTORS = {
    "Navigation": ["nav a[href]", "[role='navigation'] a[href]"],
    "Header": ["header a[href]"],
    "Footer": ["footer a[href]", "[role='contentinfo'] a[href]"],
    "CTA": [
        "a.cta", "a.btn", "a[class*='button']", "a[class*='cta']",
        "a[class*='btn']", ".hero a[href]", "section a[href][class]",
    ],
    "Body text": [
        "main p a[href]", "article a[href]", ".content a[href]", "#content a[href]",
    ],
}

# Lower rank wins when a URL appears in several zones.
_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# A pure "#fragment" is an in-page anchor, not a link to fetch — urljoin() would
# turn it into "https://site/#frag", which then looks like an http URL and gets
# pointlessly requested over the network (HTTP never sees the fragment).
_CONTACT_PREFIXES = ("mailto:", "tel:", "sms:")
# Handled by the dead-CTA detector, or not addressable at all.
_IGNORED_PREFIXES = ("javascript:", "data:", "blob:", "file:", "about:")

# Bare placeholder hrefs — dead-CTA candidates, not navigable anchors.
_BARE_FRAGMENTS = {"", "#", "#0", "#!", "#null", "#undefined"}


def _zone_map(soup) -> dict:
    """Map id(tag) -> zone for every anchor a zone selector matches.

    Selectors are applied in ZONE_SELECTORS order and the first match wins, so
    an <a> inside <nav> stays Navigation even if it also carries .btn.
    """
    zones: dict[int, str] = {}
    for zone, selectors in ZONE_SELECTORS.items():
        for selector in selectors:
            for tag in soup.select(selector):
                zones.setdefault(id(tag), zone)
    return zones


def _rank(zone: str) -> int:
    return _PRIORITY_RANK.get(ZONE_PRIORITY.get(zone, "low"), 3)


def _classify_href(href: str, page_url: str, targets: set) -> tuple:
    """(key, link_kind, resolved_url, fragment) or None if the href isn't a link.

    Returns None for bare placeholder hrefs and javascript:/data: URIs — the
    dead-CTA detector owns those. Broken in-page anchors also return None: the
    detector reports them with its own suppression rules, so listing them here
    too would double-report the same defect.
    """
    h = href.strip()
    if h.lower() in _BARE_FRAGMENTS:
        return None
    low = h.lower()
    if low.startswith(_IGNORED_PREFIXES):
        return None

    if low.startswith(_CONTACT_PREFIXES):
        return (low, "contact", h, "")

    if h.startswith("#"):
        fragment = unquote(h[1:])
        # Only surface anchors that actually resolve; unresolved ones are the
        # detector's business (it knows about functional fragments like
        # #elementor-action and about widget suppression).
        if fragment in targets or fragment.lower() in targets or is_functional_fragment(fragment):
            absolute = urljoin(page_url, h)
            return (absolute, "anchor", absolute, fragment)
        return None

    absolute = urljoin(page_url, h)
    if not absolute.startswith(("http://", "https://")):
        return None
    return (absolute, "http", absolute, urlparse(absolute).fragment)


def _collect_links(soup, url: str) -> list[RawLink]:
    """One RawLink per unique destination, carrying every zone it appears in.

    Covers http(s) links, resolving in-page anchors, and mailto:/tel: contacts —
    a link the user can see on the page should be accounted for somewhere.
    """
    zone_of = _zone_map(soup)
    targets = fragment_targets(soup)
    by_key: dict[str, RawLink] = {}

    for tag in soup.find_all("a", href=True):
        classified = _classify_href(tag["href"], url, targets)
        if classified is None:
            continue
        key, link_kind, resolved, fragment = classified

        zone = zone_of.get(id(tag), "Other")
        existing = by_key.get(key)

        if existing is None:
            by_key[key] = RawLink(
                url=resolved,
                source_element=tag.name,
                anchor_text=(tag.get_text(strip=True) or "")[:80],
                category=zone,
                is_external=(
                    link_kind == "http"
                    and urlparse(resolved).netloc != urlparse(url).netloc
                ),
                priority=ZONE_PRIORITY.get(zone, "low"),
                zones=[zone],
                occurrences=1,
                link_kind=link_kind,
                fragment=fragment,
            )
            continue

        # Same destination linked again — record the occurrence instead of
        # dropping it, and promote the row to the highest-priority zone.
        existing.occurrences += 1
        if zone not in existing.zones:
            existing.zones.append(zone)
        if not existing.anchor_text:
            existing.anchor_text = (tag.get_text(strip=True) or "")[:80]
        if _rank(zone) < _rank(existing.category):
            existing.category = zone
            existing.priority = ZONE_PRIORITY.get(zone, "low")

    return list(by_key.values())


# Reads url() references out of stylesheets the browser has actually loaded.
# Cross-origin sheets raise on .cssRules access — skipped, not fatal.
_COLLECT_STYLESHEETS_JS = r"""
() => {
  const out = [];
  for (const sheet of Array.from(document.styleSheets || [])) {
    try {
      const rules = sheet.cssRules;
      if (!rules) continue;
      let text = '';
      for (const rule of Array.from(rules)) text += rule.cssText + '\n';
      out.push({ href: sheet.href || '', text: text.slice(0, 200000) });
    } catch (e) { /* cross-origin stylesheet */ }
  }
  return out;
}
"""


def _empty_signals() -> dict:
    return {
        "console_errors": [],     # [{text, location}]
        "csp_violations": [],     # [str]
        "failed_requests": [],    # [{url, resource_type, failure}]
        "http_errors": [],        # [{url, status, resource_type}]
    }


def _scrape_sync(url: str) -> tuple[list[RawLink], list[str], dict]:
    signals = _empty_signals()

    def on_console(msg):
        if msg.type not in ("error", "warning"):
            return
        text = (msg.text or "")[:500]
        entry = {"text": text, "location": (msg.location or {}).get("url", "")}
        if "content security policy" in text.lower() or "refused to" in text.lower():
            signals["csp_violations"].append(text)
        if msg.type == "error":
            signals["console_errors"].append(entry)

    def on_request_failed(request):
        signals["failed_requests"].append({
            "url": request.url,
            "resource_type": request.resource_type,
            "failure": (request.failure or "")[:200] if isinstance(request.failure, str)
                       else str(request.failure)[:200],
        })

    def on_response(response):
        if response.status >= 400:
            signals["http_errors"].append({
                "url": response.url,
                "status": response.status,
                "resource_type": response.request.resource_type,
            })

    stylesheets = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        # Stamp elements that attach runtime click listeners so genuinely
        # interactive JS elements are not mislabeled as dead CTAs.
        page.add_init_script(LISTENER_PROBE_JS)
        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Give frameworks time to hydrate and attach their listeners.
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        html = page.content()
        try:
            stylesheets = page.evaluate(_COLLECT_STYLESHEETS_JS)
        except Exception:
            stylesheets = []
        browser.close()

    soup = BeautifulSoup(html, "lxml")

    results: list[RawLink] = _collect_links(soup, url)
    results.extend(find_dead_ctas(soup, url))
    results.extend(merge_resources(
        collect_resources(soup, url),
        resources_from_stylesheets(stylesheets, url),
        already_seen={r.url for r in results},
    ))

    builders = [b["name"] for b in detect_builders(soup)]
    return results, builders, signals


def merge_resources(dom_resources, stylesheet_resources, already_seen) -> list:
    """Resources not already covered by the anchor pass, deduped by URL."""
    merged: dict = {}
    for resource in list(dom_resources) + list(stylesheet_resources):
        if resource.url in already_seen or resource.url in merged:
            continue
        merged[resource.url] = resource
    return list(merged.values())


async def scrape_links(url: str) -> tuple[list[RawLink], list[str], dict]:
    """Scrape a page. Returns (links_and_resources, builders, runtime_signals)."""
    import asyncio
    return await asyncio.to_thread(_scrape_sync, url)
