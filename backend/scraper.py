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

# All values that mean "this goes nowhere"
DEAD_HREF_VALUES = {
    "", "#", "#0", "#!", "#null", "#undefined",
    "javascript:", "javascript:void(0)", "javascript:void(0);",
    "javascript:;", "javascript:return false;",
    "javascript:return false", "javascript:null",
    "void(0)", "#link", "#anchor",
}

# CSS class keywords that indicate something is styled as a button/CTA
CTA_CLASS_KEYWORDS = [
    "btn", "button", "cta", "call-to-action",
    "action", "signup", "sign-up", "register",
    "get-started", "getstarted", "try-free",
    "start-free", "learn-more", "learnmore",
    "buy-now", "buynow", "order-now", "ordernow",
    "subscribe", "download", "free-trial",
    "book-demo", "bookdemo", "contact-us",
    "hero__cta", "primary", "secondary",
]


def _is_dead_href(href: str) -> bool:
    """Check if an href value means the link goes nowhere."""
    if not href:
        return True
    href = href.strip().lower()
    if href in DEAD_HREF_VALUES:
        return True
    if href.startswith("javascript:"):
        return True
    if href == "#" or (href.startswith("#") and len(href) <= 2):
        return True
    return False


def _has_cta_class(tag) -> bool:
    """Check if a tag has any class that looks like a CTA or button."""
    classes = tag.get("class", [])
    if isinstance(classes, str):
        classes = classes.split()
    class_str = " ".join(classes).lower()
    return any(keyword in class_str for keyword in CTA_CLASS_KEYWORDS)


def get_nearest_heading(tag) -> str:
    """Walk up and sideways in DOM to find nearest heading above this element."""
    for parent in tag.parents:
        for sibling in parent.previous_siblings:
            if not hasattr(sibling, 'name') or sibling.name is None:
                continue
            if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                text = sibling.get_text(strip=True)
                if text:
                    return f"Near: {text[:60]}"
            heading = (
                sibling.find('h1') or sibling.find('h2') or
                sibling.find('h3') or sibling.find('h4')
            )
            if heading:
                text = heading.get_text(strip=True)
                if text:
                    return f"Near: {text[:60]}"
        if hasattr(parent, 'name') and parent.name in ['section', 'div']:
            aria = parent.get('aria-label', '').strip()
            if aria:
                return f"In: {aria[:60]}"
    return "Location unknown"


def _find_dead_ctas(soup, url: str) -> list[RawLink]:
    dead: list[RawLink] = []
    seen: set[str] = set()

    # Strategy 1: Find ALL anchor tags with dead hrefs
    for tag in soup.find_all("a"):
        href = tag.get("href", "").strip()
        if not _is_dead_href(href):
            continue

        anchor = (tag.get_text(strip=True) or "")[:80]
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

    # Strategy 2: Find button tags with no real action
    for tag in soup.find_all("button"):
        onclick = tag.get("onclick", "").strip().lower()
        tag_type = tag.get("type", "button").lower()

        # Skip actual submit/reset buttons
        if tag_type in ["submit", "reset"]:
            continue

        # Skip buttons that actually do something real
        if onclick and not any(dead_val in onclick for dead_val in [
            "void(0)", "return false", "javascript:", "#"
        ]):
            continue

        anchor = (tag.get_text(strip=True) or "")[:80]
        key = f"btn_{anchor}_{onclick}"
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

    # Strategy 3: Find divs/spans acting as buttons with no real action
    for tag_name in ["div", "span", "li"]:
        for tag in soup.find_all(tag_name):
            role = tag.get("role", "").lower()
            onclick = tag.get("onclick", "").strip().lower()

            is_button_role = role == "button"
            has_cta_cls = _has_cta_class(tag)
            has_dead_onclick = onclick and any(dead_val in onclick for dead_val in [
                "void(0)", "return false", "#"
            ])
            has_no_action = is_button_role and not onclick

            if not (is_button_role or (has_cta_cls and (has_dead_onclick or has_no_action))):
                continue

            anchor = (tag.get_text(strip=True) or "")[:80]
            # Skip if text is too long (probably not a button)
            if len(anchor) > 50:
                continue

            key = f"div_{anchor}_{onclick}"
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
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
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
    import asyncio
    return await asyncio.to_thread(_scrape_sync, url)