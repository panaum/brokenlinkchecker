import httpx
import xml.etree.ElementTree as ET
import os
from urllib.parse import urlparse, urljoin
import asyncio
from scraper import scrape_links

EXCLUDED_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.zip', '.gz',
    '.css', '.js', '.xml', '.json', '.ico', '.webp', '.mp4', '.mp3',
    '.wav', '.avi', '.mov', '.dmg', '.pkg', '.txt', '.woff', '.woff2',
    '.ttf', '.eot', '.csv', '.xlsx', '.doc', '.docx', '.ppt', '.pptx'
}

def is_html_url(url: str) -> bool:
    """Filter out known non-HTML resources by file extension."""
    parsed = urlparse(url)
    path = parsed.path
    _, ext = os.path.splitext(path.lower())
    if ext in EXCLUDED_EXTENSIONS:
        return False
    return True

def clean_url(url: str) -> str:
    """Strip fragment from URL and normalize."""
    parsed = urlparse(url)
    # Reconstruct without fragment
    return parsed._replace(fragment="").geturl()

async def parse_sitemap(sitemap_url: str, client: httpx.AsyncClient) -> list[str]:
    """Fetch and parse a sitemap. Returns nested sitemap URLs or page URLs."""
    try:
        resp = await client.get(sitemap_url, timeout=10.0, follow_redirects=True)
        if resp.status_code != 200:
            return []
        
        # Parse XML
        root = ET.fromstring(resp.content)
        
        # Check if it is a sitemap index or urlset
        # We look for loc elements inside sitemap or url elements
        urls = []
        
        # XML namespaces can vary, so we search dynamically
        sitemaps = root.findall('.//{*}sitemap')
        if sitemaps:
            # It's a sitemap index, recursively fetch child sitemaps
            tasks = []
            for s in sitemaps:
                loc_el = s.find('{*}loc')
                if loc_el is not None and loc_el.text:
                    tasks.append(parse_sitemap(loc_el.text.strip(), client))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    urls.extend(res)
            return urls
        
        url_elements = root.findall('.//{*}url')
        for u in url_elements:
            loc_el = u.find('{*}loc')
            if loc_el is not None and loc_el.text:
                urls.append(loc_el.text.strip())
        
        return urls
    except Exception as e:
        print(f"[Sitemap] Error parsing {sitemap_url}: {e}")
        return []

async def crawl_site(base_url: str, max_pages: int) -> list[str]:
    """Crawl homepage up to depth 2 as fallback."""
    print(f"[Crawler] Starting fallback crawl on {base_url}")
    base_parsed = urlparse(base_url)
    base_domain = base_parsed.netloc
    
    discovered = {clean_url(base_url)}
    # Queue stores tuples of (url, current_depth)
    queue = [(clean_url(base_url), 0)]
    
    while queue and len(discovered) < max_pages:
        current_url, depth = queue.pop(0)
        if depth >= 2:
            continue
            
        try:
            links = await scrape_links(current_url)
            for raw_link in links:
                if len(discovered) >= max_pages:
                    break
                
                url = clean_url(raw_link.url)
                parsed = urlparse(url)
                
                # Check same domain, html-only, not external, not already discovered
                if (parsed.netloc == base_domain and 
                    is_html_url(url) and 
                    not raw_link.is_external and 
                    url not in discovered):
                    
                    discovered.add(url)
                    queue.append((url, depth + 1))
        except Exception as e:
            print(f"[Crawler] Failed to scrape {current_url}: {e}")
            
    return list(discovered)

async def discover_site_urls(base_url: str, max_pages: int = 100) -> list[str]:
    """Main discovery entrypoint: tries sitemap.xml first, then crawls."""
    # Ensure trailing slash for sitemap detection if none exists, or construct clean path
    parsed_base = urlparse(base_url)
    if not parsed_base.path or parsed_base.path == "/":
        sitemap_url = urljoin(base_url, "/sitemap.xml")
    else:
        sitemap_url = f"{base_url.rstrip('/')}/sitemap.xml"
        
    discovered_urls = []
    
    async with httpx.AsyncClient() as client:
        discovered_urls = await parse_sitemap(sitemap_url, client)
        
    if discovered_urls:
        print(f"[Sitemap] Discovered {len(discovered_urls)} URLs from sitemap index/urlset")
        # Filter same domain and HTML only
        base_domain = parsed_base.netloc
        filtered = []
        for url in discovered_urls:
            url = clean_url(url)
            parsed = urlparse(url)
            if parsed.netloc == base_domain and is_html_url(url):
                filtered.append(url)
        
        # Deduplicate
        filtered = list(dict.fromkeys(filtered))
        return filtered[:max_pages]
        
    # Fallback to crawler
    urls = await crawl_site(base_url, max_pages)
    return urls[:max_pages]
