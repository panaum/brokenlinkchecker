from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from models import RawLink
from dead_cta_detector import find_dead_ctas, LISTENER_PROBE_JS

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


def _scrape_sync(url: str) -> list[RawLink]:
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
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Give frameworks time to hydrate and attach their listeners.
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    seen_hrefs: set[str] = set()
    results: list[RawLink] = []

    for zone, selectors in ZONE_SELECTORS.items():
        for selector in selectors:
            for tag in soup.select(selector):
                href = tag.get("href", "").strip()
                if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                    continue
                absolute = urljoin(url, href)
                if absolute in seen_hrefs:
                    continue
                seen_hrefs.add(absolute)
                results.append(RawLink(
                    url=absolute,
                    source_element=selector,
                    anchor_text=(tag.get_text(strip=True) or "")[:80],
                    category=zone,
                    is_external=urlparse(absolute).netloc != urlparse(url).netloc,
                    priority=ZONE_PRIORITY.get(zone, "low"),
                ))
    for tag in soup.find_all("a", href=True):
        href = urljoin(url, tag["href"].strip())
        if href not in seen_hrefs and href.startswith("http"):
            seen_hrefs.add(href)
            results.append(RawLink(
                url=href,
                source_element="a",
                anchor_text=(tag.get_text(strip=True) or "")[:80],
                category="Other",
                is_external=urlparse(href).netloc != urlparse(url).netloc,
                priority="low",
            ))
    dead_ctas = find_dead_ctas(soup, url)
    results.extend(dead_ctas)
    return results


async def scrape_links(url: str) -> list[RawLink]:
    import asyncio
    return await asyncio.to_thread(_scrape_sync, url)
