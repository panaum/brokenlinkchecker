import asyncio
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from models import RawLink

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

def _find_dead_ctas(soup, url: str) -> list[RawLink]:
    dead: list[RawLink] = []
    seen: set[str] = set()

    cta_selectors = [
        "a[class*='button']", "a[class*='btn']", "a[class*='cta']",
        "a.btn", "a.cta", "a[role='button']",
    ]

    def get_nearest_heading(tag) -> str:
        """Walk up and sideways in DOM to find nearest heading above this element"""
        # First check siblings and parents for nearby headings
        for parent in tag.parents:
            # Look at previous siblings of each parent
            for sibling in parent.previous_siblings:
                if hasattr(sibling, 'name'):
                    if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                        text = sibling.get_text(strip=True)
                        if text:
                            return f"Near: {text[:60]}"
                    # Also check headings inside siblings
                    heading = sibling.find('h1') or sibling.find('h2') or sibling.find('h3') or sibling.find('h4')
                    if heading:
                        text = heading.get_text(strip=True)
                        if text:
                            return f"Near: {text[:60]}"
            # Check if parent itself is a section/div with an id or aria-label
            if hasattr(parent, 'name') and parent.name in ['section', 'div']:
                aria = parent.get('aria-label', '').strip()
                if aria:
                    return f"In: {aria[:60]}"
        return "Location unknown"

    for selector in cta_selectors:
        for tag in soup.select(selector):
            href = tag.get("href", "").strip()
            anchor = (tag.get_text(strip=True) or "")[:80]

            is_dead = (
                not href
                or href == "#"
                or href == "javascript:void(0)"
                or href == "javascript:"
                or href == "#0"
                or href == "#!"
            )

            if not is_dead:
                continue

            key = f"{anchor}_{href}"
            if key in seen:
                continue
            seen.add(key)

            location = get_nearest_heading(tag)

            dead.append(RawLink(
                url=url,
                source_element=location,
                anchor_text=anchor or "[no text]",
                category="Dead CTA",
                is_external=False,
            ))

    return dead

def _scrape_sync(url: str) -> list[RawLink]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (compatible; LinkCheckerBot/1.0)"
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
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
            ))

    dead_ctas = _find_dead_ctas(soup, url)
    results.extend(dead_ctas)
    return results

async def scrape_links(url: str) -> list[RawLink]:
    return await asyncio.to_thread(_scrape_sync, url)