"""X-ray capture — a full-page screenshot plus the on-page geometry of every
clickable element, so the report can draw crosshair markers on the real page.

This is DELIBERATELY separate from the scan render (scraper._scrape_sync): it is
a best-effort, on-demand capture invoked when the user opens the X-ray view. That
keeps it fully additive — if it fails, or Playwright isn't available, the report
degrades to a plain findings list and no scan is ever affected.

The frontend matches findings to these boxes by URL / anchor text, so we don't
need to know which elements are "flagged" at capture time — we return them all.
"""
import base64

# Bounding boxes for every clickable thing, in FULL-PAGE (document) coordinates
# at a known viewport width. Coordinates already include scroll offset so they
# line up with a full_page screenshot captured from the document origin.
_COLLECT_BOXES_JS = r"""
() => {
  const out = [];
  const sel = 'a[href], button, [role="button"], input[type="submit"], input[type="button"], [onclick]';
  const seen = new Set();
  const sx = window.scrollX || 0, sy = window.scrollY || 0;
  document.querySelectorAll(sel).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return;            // invisible / collapsed
    const x = Math.round(r.left + sx), y = Math.round(r.top + sy);
    const w = Math.round(r.width), h = Math.round(r.height);
    let url = '';
    try { url = el.getAttribute('href') || ''; } catch (e) {}
    // Resolve relative hrefs the way the scanner records them.
    if (url && !/^([a-z]+:|#|\/\/)/i.test(url)) {
      try { url = new URL(url, document.baseURI).href; } catch (e) {}
    }
    const text = (el.innerText || el.textContent || el.value || '').trim().slice(0, 120);
    const key = url + '|' + text + '|' + x + ',' + y;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ url, text, tag: el.tagName.toLowerCase(), x, y, w, h });
  });
  return out;
}
"""


def capture_xray_sync(url: str, viewport_width: int = 1280) -> dict:
    """Launch a headless page, screenshot it full-page, and collect element
    boxes. Returns a dict; on any failure returns {available: False, error}.
    Never raises."""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": viewport_width, "height": 900},
                device_scale_factor=1,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            page.wait_for_timeout(800)

            # Measure the full document so the frontend can scale the overlay.
            dims = page.evaluate(
                "() => ({ w: Math.max(document.documentElement.scrollWidth, "
                "document.body ? document.body.scrollWidth : 0), "
                "h: Math.max(document.documentElement.scrollHeight, "
                "document.body ? document.body.scrollHeight : 0) })"
            )
            try:
                elements = page.evaluate(_COLLECT_BOXES_JS)
            except Exception:
                elements = []
            shot = page.screenshot(type="png", full_page=True)
            browser.close()

        return {
            "available": True,
            "screenshot": base64.b64encode(shot).decode("utf-8"),
            "viewport_width": viewport_width,
            "page_width": int(dims.get("w") or viewport_width),
            "page_height": int(dims.get("h") or 0),
            "elements": elements,
        }
    except Exception as e:  # noqa: BLE001 — best-effort by design
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
