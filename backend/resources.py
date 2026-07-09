"""
Page resource extraction.

A link checker that only follows <a href> misses the failures users actually
notice: a 404 on a <script src> breaks every interaction on the page, and a
dead <link rel=stylesheet> makes it unreadable. Those are silent today — the
page still returns 200.

Pure functions over a parsed DOM. No Playwright, no network.
"""
import re
from urllib.parse import urljoin, urlparse

from models import RawLink


# ─── Resource taxonomy ───────────────────────────────────────────────────────
# Drives the "Link Types" panel. `anchor` is what the crawler already handled.
ANCHOR = "anchor"
IMAGE = "image"
SCRIPT = "script"
STYLESHEET = "stylesheet"
CSS_URL = "css_url"
IFRAME = "iframe"
MEDIA = "media"
META_IMAGE = "meta_image"
FAVICON = "favicon"
OTHER = "other"

RESOURCE_LABELS = {
    ANCHOR: "<a href>",
    IMAGE: "<img src>",
    SCRIPT: "<script src>",
    STYLESHEET: "<link stylesheet>",
    CSS_URL: "CSS url()",
    IFRAME: "iframe",
    MEDIA: "media",
    META_IMAGE: "social/meta image",
    FAVICON: "favicon",
    OTHER: "other",
}

# Why a broken resource of this type matters. Deterministic copy — no LLM.
RESOURCE_IMPACT = {
    SCRIPT: "breaks page behaviour",
    STYLESHEET: "breaks page rendering",
    IMAGE: "shows a broken image to visitors",
    CSS_URL: "a background or font asset fails to load",
    IFRAME: "an embedded panel fails to load",
    MEDIA: "audio or video fails to play",
    META_IMAGE: "link previews on social platforms break",
    FAVICON: "the browser tab icon is missing",
    OTHER: "an asset fails to load",
}

# A broken script or stylesheet stops the page working, not just looking wrong.
HIGH_PRIORITY_RESOURCES = frozenset({SCRIPT, STYLESHEET})

# Rendering breaks; these never carry meaningful anchor text.
_RESOURCE_ZONE = "Resource"

_NON_FETCHABLE = ("data:", "blob:", "javascript:", "about:", "mailto:", "tel:")

# url(...) in CSS: single, double or unquoted, ignoring data: URIs.
_CSS_URL_RE = re.compile(r"""url\(\s*(?:'([^']*)'|"([^"]*)"|([^)'"]*))\s*\)""", re.IGNORECASE)

_IMPORT_RE = re.compile(r"""@import\s+(?:url\(\s*)?(?:'([^']*)'|"([^"]*)")""", re.IGNORECASE)


def describe_resource_failure(resource_type: str) -> str:
    """Reason text for a broken resource, e.g. for a dead <script src>."""
    label = RESOURCE_LABELS.get(resource_type, RESOURCE_LABELS[OTHER])
    impact = RESOURCE_IMPACT.get(resource_type, RESOURCE_IMPACT[OTHER])
    return f"Broken {label} — {impact}"


def _is_fetchable(raw: str) -> bool:
    if not raw:
        return False
    value = raw.strip()
    if not value or value.startswith("#"):
        return False
    return not value.lower().startswith(_NON_FETCHABLE)


def _absolute(base: str, raw: str) -> str:
    return urljoin(base, raw.strip())


def parse_srcset(value: str) -> list:
    """`a.png 1x, b.png 2x` -> ['a.png', 'b.png']. Descriptors are dropped."""
    out = []
    for candidate in (value or "").split(","):
        url = candidate.strip().split()[0] if candidate.strip() else ""
        if url:
            out.append(url)
    return out


def extract_css_urls(css_text: str, base_url: str) -> list:
    """Absolute URLs referenced by url() and @import in a stylesheet."""
    found = []
    for match in _CSS_URL_RE.finditer(css_text or ""):
        raw = next((g for g in match.groups() if g is not None), "")
        if _is_fetchable(raw):
            found.append(_absolute(base_url, raw))
    for match in _IMPORT_RE.finditer(css_text or ""):
        raw = next((g for g in match.groups() if g is not None), "")
        if _is_fetchable(raw):
            found.append(_absolute(base_url, raw))
    return found


def _rels(tag) -> set:
    rel = tag.get("rel") or []
    if isinstance(rel, str):
        rel = rel.split()
    return {r.lower() for r in rel}


def _resource(url: str, page_url: str, resource_type: str, element: str) -> RawLink:
    return RawLink(
        url=url,
        source_element=element,
        anchor_text=RESOURCE_LABELS.get(resource_type, resource_type),
        category=_RESOURCE_ZONE,
        is_external=urlparse(url).netloc != urlparse(page_url).netloc,
        # Cleared by the checker if the resource turns out to be healthy.
        priority="high" if resource_type in HIGH_PRIORITY_RESOURCES else "low",
        zones=[_RESOURCE_ZONE],
        link_kind="http",
        resource_type=resource_type,
    )


def collect_resources(soup, page_url: str) -> list:
    """Every fetchable non-anchor resource the page references, deduped by URL."""
    found: dict = {}

    def add(raw: str, resource_type: str, element: str) -> None:
        if not _is_fetchable(raw):
            return
        absolute = _absolute(page_url, raw)
        if not absolute.lower().startswith(("http://", "https://")):
            return
        # First sighting wins, except that a higher-priority type upgrades the
        # row: the same URL used as both an <img> and a <script> should be
        # reported with the consequence that actually breaks the page.
        existing = found.get(absolute)
        if existing is None:
            found[absolute] = _resource(absolute, page_url, resource_type, element)
        elif (resource_type in HIGH_PRIORITY_RESOURCES
              and existing.resource_type not in HIGH_PRIORITY_RESOURCES):
            found[absolute] = _resource(absolute, page_url, resource_type, element)

    for tag in soup.find_all("img"):
        add(tag.get("src", ""), IMAGE, "img")
        for candidate in parse_srcset(tag.get("srcset", "")):
            add(candidate, IMAGE, "img[srcset]")

    for tag in soup.find_all("script", src=True):
        add(tag["src"], SCRIPT, "script")

    for tag in soup.find_all("link", href=True):
        rels = _rels(tag)
        if "stylesheet" in rels:
            add(tag["href"], STYLESHEET, "link[rel=stylesheet]")
        elif "icon" in rels or "shortcut" in rels or "apple-touch-icon" in rels:
            add(tag["href"], FAVICON, "link[rel=icon]")
        elif "preload" in rels and (tag.get("as") or "").lower() in {"script", "style", "font"}:
            add(tag["href"], OTHER, "link[rel=preload]")

    for tag in soup.find_all("iframe", src=True):
        add(tag["src"], IFRAME, "iframe")

    for name in ("video", "audio"):
        for tag in soup.find_all(name):
            add(tag.get("src", ""), MEDIA, name)
            add(tag.get("poster", ""), IMAGE, f"{name}[poster]")

    for tag in soup.find_all("source"):
        add(tag.get("src", ""), MEDIA, "source")
        for candidate in parse_srcset(tag.get("srcset", "")):
            add(candidate, IMAGE, "source[srcset]")

    # Social preview images. og:image uses `property`, twitter:image uses `name`.
    for tag in soup.find_all("meta"):
        key = (tag.get("property") or tag.get("name") or "").lower()
        if key in {"og:image", "og:image:url", "og:image:secure_url", "twitter:image",
                   "twitter:image:src"}:
            add(tag.get("content", ""), META_IMAGE, f"meta[{key}]")

    # CSS url() from inline <style> blocks and style="" attributes.
    for tag in soup.find_all("style"):
        for url in extract_css_urls(tag.get_text() or "", page_url):
            add(url, CSS_URL, "style")

    for tag in soup.find_all(style=True):
        for url in extract_css_urls(tag.get("style") or "", page_url):
            add(url, CSS_URL, "[style]")

    return list(found.values())


def resources_from_stylesheets(sheets: list, page_url: str) -> list:
    """RawLinks for url() references collected from linked stylesheets.

    `sheets` is [{"href": str, "text": str}] gathered at runtime — a linked
    stylesheet's rules are only readable once the browser has loaded it.
    """
    found: dict = {}
    for sheet in sheets or []:
        base = sheet.get("href") or page_url
        for url in extract_css_urls(sheet.get("text") or "", base):
            if url not in found:
                found[url] = _resource(url, page_url, CSS_URL, "stylesheet url()")
    return list(found.values())


# ─── Overview panels ─────────────────────────────────────────────────────────
def link_type_breakdown(results) -> dict:
    """Counts per resource type, for the Link Types panel."""
    counts = {}
    for r in results:
        rtype = _get(r, "resource_type") or ANCHOR
        counts[rtype] = counts.get(rtype, 0) + 1
    return counts


def scheme_breakdown(results) -> dict:
    """https / http / mailto / tel / data counts."""
    counts = {}
    for r in results:
        scheme = (urlparse(_get(r, "url") or "").scheme or "other").lower()
        counts[scheme] = counts.get(scheme, 0) + 1
    return counts


def host_breakdown(results, limit: int = 10) -> list:
    """[{host, count}] sorted by count desc, then host, for the Top Hosts panel."""
    counts = {}
    for r in results:
        host = urlparse(_get(r, "url") or "").netloc.lower()
        if not host:
            continue   # mailto:/tel: have no host
        counts[host] = counts.get(host, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"host": h, "count": c} for h, c in ranked[:limit]]


def _get(result, field):
    if isinstance(result, dict):
        return result.get(field)
    return getattr(result, field, None)
