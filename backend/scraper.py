import re
import time

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
from form_audit import form_action_links
from tracking_audit import extract_tracking
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


# Read-only inventory of every <form> on the rendered page.
#
# THIS NEVER SUBMITS ANYTHING. It reads attributes, computed styles, bounding
# boxes and elementFromPoint. There is no .submit(), no .requestSubmit(), no
# .click(), and no synthetic event anywhere in this script. A form audit that
# submits would spam a client's CRM, which is the one outcome worse than a
# broken form.
#
# `getAttribute('action')` is deliberate: form.action returns the PAGE URL when
# the attribute is absent, which would make every action-less form look like it
# posts to itself.
_COLLECT_FORMS_JS = r"""
() => {
  const SUBMIT_SELECTOR = [
    'button[type=submit]',
    'input[type=submit]',
    'input[type=image]',
    'button:not([type])',          // HTML spec: implicit submit
    '[role=button][data-submit]',
  ].join(',');

  // Why a form is not visible matters. "display:none" is the resting state of
  // every modal contact form; "rendered at zero size" is a rendering failure.
  const hiddenReason = (el, rect, style) => {
    if (style.display === 'none') return 'css';
    if (style.visibility === 'hidden') return 'css';
    if (parseFloat(style.opacity || '1') === 0) return 'css';
    if (el.hidden) return 'css';
    if (!el.offsetParent && style.position !== 'fixed') return 'css';
    if (rect.width < 2 || rect.height < 2) return 'zero-size';
    return '';
  };

  const isCovered = (form, rect) => {
    // Something painted on top of the form's centre point. A cookie wall or a
    // modal backdrop makes a form unreachable without changing its styles.
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) {
      return null;   // off-screen: cannot tell, do not guess
    }
    const top = document.elementFromPoint(x, y);
    if (!top) return null;
    return !(form.contains(top) || top.contains(form));
  };

  const label = (form) => {
    const aria = form.getAttribute('aria-label');
    if (aria) return aria.trim().slice(0, 60);
    if (form.id) return form.id.trim().slice(0, 60);
    if (form.name) return form.name.trim().slice(0, 60);
    const heading = form.querySelector('legend, h1, h2, h3, h4');
    if (heading && heading.textContent.trim()) {
      return heading.textContent.trim().slice(0, 60);
    }
    const submit = form.querySelector('button, input[type=submit]');
    if (submit) {
      const text = (submit.value || submit.textContent || '').trim();
      if (text) return text.slice(0, 60);
    }
    return '';
  };

  const forms = Array.from(document.querySelectorAll('form'));
  return forms.map((form, index) => {
    const style = window.getComputedStyle(form);
    const rect = form.getBoundingClientRect();
    const reason = hiddenReason(form, rect, style);
    const visible = reason === '';

    const controls = Array.from(form.elements || []);
    const fields = controls
      .filter((el) => ['input', 'select', 'textarea'].includes(el.tagName.toLowerCase()))
      .map((el) => ({
        tag: el.tagName.toLowerCase(),
        type: (el.getAttribute('type') || '').toLowerCase(),
        name: el.getAttribute('name') || '',
        id: el.id || '',
        placeholder: el.getAttribute('placeholder') || '',
        required: !!(el.required || el.getAttribute('aria-required') === 'true'),
      }));
    const required = fields.filter((f) => f.required);

    return {
      index: index,
      identifier: form.id || form.name || '',
      label: label(form),
      role: form.getAttribute('role') || '',
      fields: fields,
      hidden_reason: reason,
      action_raw: form.getAttribute('action'),        // null when absent
      method: (form.getAttribute('method') || 'get').toLowerCase(),
      // Resolved by the browser, so relative actions are already absolute.
      action_url: form.getAttribute('action') ? form.action : '',
      has_submit: !!form.querySelector(SUBMIT_SELECTOR),
      has_inline_onsubmit: !!form.getAttribute('onsubmit'),
      has_js_submit_listener: form.hasAttribute('data-js-listener'),
      field_count: controls.length,
      required_fields: required,
      visible: visible,
      covered: visible ? isCovered(form, rect) : null,
      // Scripts that render a form for you. If one 404s, the form never appears.
      embed_scripts: Array.from(document.querySelectorAll('script[src]'))
        .map((s) => s.src)
        .filter((src) =>
          /hs-scripts\.com|hsforms\.net|js\.hsforms\.net|embed\.typeform\.com|form\.jotform|forms\.gle|paperform|formstack|wufoo|gravityforms|marketo|munchkin\.js|pardot|leadconnectorhq|msgsndr/i.test(src)
        ),
      has_embed_container: !!document.querySelector(
        '.hs-form, .hs-form-frame, [data-hs-forms], [data-form-id], .typeform-widget, .jotform-form, [data-formstack]'
      ),
    };
  });
}
"""


# Formless forms. React, Vue and most page builders ship lead capture as a plain
# <div> holding inputs and a button — no <form> tag at all, submitted with fetch.
# `document.querySelectorAll('form')` finds none of them.
#
# A container qualifies only if it holds at least one typable field AND a
# clickable whose text reads like a submit control. Still read-only: this maps
# the DOM, it does not press anything.
_COLLECT_FORMLESS_JS = r"""
() => {
  const TYPABLE = 'input:not([type=hidden]):not([type=submit]):not([type=button])' +
                  ':not([type=image]):not([type=reset]), textarea, select';
  const CLICKABLE = 'button, [role=button], input[type=button], a:not([href])';
  // A two-step order form's step-1 button reads "Go To Step #2". A checkout's
  // reads "Continue". Matching only /submit|send/ found neither.
  const SUBMITISH = new RegExp(
    '(send|submit|subscribe|sign\\s*up|get\\s+started|join|register|request|apply' +
    '|book|contact|enquir|inquir|get\\s+in\\s+touch|continue|next\\s+step|go\\s+to\\s+step' +
    '|proceed|claim|reserve|order|checkout|enrol|count\\s+me\\s+in|secure\\s+my|get\\s+my)',
    'i');
  // A container holding an email or phone box is capturing a lead whatever its
  // button says. That is the structural signal, for buttons no wordlist catches.
  const LEAD_FIELD = 'input[type=email], input[type=tel]';

  const textOf = (el) => (el.value || el.innerText || el.textContent || '').trim();

  const submitish = (root) => {
    const clickables = Array.from(root.querySelectorAll(CLICKABLE));
    const byText = clickables.find((c) => SUBMITISH.test(textOf(c)));
    if (byText) return byText;
    if (root.querySelector(LEAD_FIELD)) return clickables.find((c) => textOf(c));
    return undefined;
  };

  // Walk up from a stray input until an ancestor also holds a submit-ish button.
  const containerFor = (input) => {
    let el = input.parentElement;
    for (let hops = 0; el && hops < 8; hops++, el = el.parentElement) {
      if (el === document.body || el === document.documentElement) return null;
      if (submitish(el)) return el;
    }
    return null;
  };

  const strays = Array.from(document.querySelectorAll(TYPABLE))
    .filter((i) => !i.closest('form'));

  const containers = [];
  for (const input of strays) {
    const c = containerFor(input);
    if (c && !containers.includes(c)) containers.push(c);
  }

  return containers.map((c, index) => {
    const style = window.getComputedStyle(c);
    const rect = c.getBoundingClientRect();
    let reason = '';
    if (style.display === 'none' || style.visibility === 'hidden') reason = 'css';
    else if (rect.width < 2 || rect.height < 2) reason = 'zero-size';

    const button = submitish(c);
    const fields = Array.from(c.querySelectorAll('input, textarea, select')).map((el) => ({
      tag: el.tagName.toLowerCase(),
      type: (el.getAttribute('type') || '').toLowerCase(),
      name: el.getAttribute('name') || '',
      id: el.id || '',
      placeholder: el.getAttribute('placeholder') || '',
      required: !!(el.required || el.getAttribute('aria-required') === 'true'),
    }));

    // The button names the form ("Get Started"); a heading names the page around
    // it. wix.com's container reached up to an <h1> reading "The new way to
    // create a website", which is not what anyone would call that form.
    const heading = c.querySelector('h1, h2, h3, h4, legend');
    return {
      index: index,
      synthetic: true,                  // no <form> tag; rules that assume one must not fire
      identifier: c.id || '',
      label: (c.getAttribute('aria-label') || (button && textOf(button)) ||
              (heading && heading.textContent) || '').trim().slice(0, 60),
      role: c.getAttribute('role') || '',
      fields: fields,
      hidden_reason: reason,
      action_raw: null,
      method: '',
      action_url: '',
      has_submit: !!button,
      has_inline_onsubmit: !!(button && button.getAttribute('onclick')),
      // The listener probe stamps elements that registered a click listener.
      has_js_submit_listener: !!(button && button.hasAttribute('data-js-listener')),
      field_count: fields.length,
      required_fields: fields.filter((f) => f.required),
      visible: reason === '',
      covered: null,
      embed_scripts: [],
      has_embed_container: false,
    };
  });
}
"""


def _empty_signals() -> dict:
    return {
        "console_errors": [],     # [{text, location}]
        "csp_violations": [],     # [str]
        "failed_requests": [],    # [{url, resource_type, failure}]
        "http_errors": [],        # [{url, status, resource_type}]
        "forms": [],              # [FormInfo] — read-only, never submitted
        "delegated": False,       # a document-level listener (React & co)
    }


# ─────────────────────────────────────────────────────────────────────────────
# Revealing a form that a CTA builds on click.
#
# Some pages hold no form at all until a button is pressed — a GoHighLevel page
# with "Join The Next Cohort" has zero <input> elements in any frame until then.
# There is nothing to read, so reading harder cannot find it.
#
# We press the CTA. WE DO NOT PRESS A FORM. Everything below exists to make that
# distinction enforceable rather than aspirational:
#
#   * the element must not be inside a <form>          (_SAFE_TO_CLICK_JS)
#   * it must not be type=submit / image / reset       (_SAFE_TO_CLICK_JS)
#   * it must not carry an href — that is a link       (_SAFE_TO_CLICK_JS)
#   * every non-GET request is aborted while we do it  (_block_non_get)
#   * every navigation away from the page is aborted   (_block_non_get)
#   * dialogs are dismissed, popups are closed
#
# A form cannot be submitted without either a non-GET request or a navigation,
# and both are blocked at the transport. The click reveals; it cannot send.
# ─────────────────────────────────────────────────────────────────────────────
_REVEAL_SELECTOR = "button, [role=button], input[type=button]"

_CTA_TEXT_RE = re.compile(
    r"(join|book|get\s+started|start\s+here|contact|apply|demo|sign\s*up|subscribe"
    r"|register|enquir|inquir|quote|request|talk\s+to|get\s+in\s+touch|free\s+)",
    re.I,
)

_SAFE_TO_CLICK_JS = r"""(el) => {
  if (el.closest('form')) return false;                 // never touch a real form
  const t = (el.getAttribute('type') || '').toLowerCase();
  if (t === 'submit' || t === 'image' || t === 'reset') return false;
  if (el.hasAttribute('href')) return false;            // a link: the checker owns it
  if (el.hasAttribute('download')) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return false;
  const s = getComputedStyle(el);
  return s.display !== 'none' && s.visibility !== 'hidden';
}"""

MAX_REVEAL_CLICKS = 6
REVEAL_BUDGET_SECONDS = 20


# Analytics fires on click. A conversion pixel is a GET, so blocking non-GET is
# not enough: pressing a CTA would log a visitor who does not exist and inflate
# the client's click-through on their own funnel. We are auditing their site,
# not participating in it.
_ANALYTICS_HOSTS = (
    "google-analytics.com", "googletagmanager.com", "analytics.google.com",
    "doubleclick.net", "googleadservices.com", "googlesyndication.com",
    "facebook.com/tr", "facebook.net", "connect.facebook",
    "segment.io", "segment.com", "mixpanel.com", "amplitude.com",
    "hotjar.com", "hotjar.io", "clarity.ms", "fullstory.com", "logrocket",
    "analytics.tiktok.com", "ads.linkedin.com", "px.ads", "bat.bing.com",
    "matomo", "plausible.io", "posthog.com", "heap.io", "intercom.io",
    "leadconnectorhq.com/tracking", "msgsndr.com/tracking",
)


def _is_analytics(url: str) -> bool:
    low = url.lower()
    return any(host in low for host in _ANALYTICS_HOSTS)


def _block_non_get(route) -> None:
    """Abort anything that could send data, leave the page, or be counted.

    Fails closed: if we cannot tell what a request is, it does not go out.
    """
    try:
        request = route.request
        if request.method.upper() != "GET":
            route.abort()
            return
        if _is_analytics(request.url):
            route.abort()
            return
        if request.is_navigation_request() and request.frame.parent_frame is None:
            route.abort()
            return
    except Exception:
        route.abort()
        return
    route.continue_()


_NEVER_CLICK_TYPES = frozenset({"submit", "image", "reset"})


def _click_is_safe(el) -> bool:
    """Two independent checks must agree before anything is pressed.

    The DOM predicate runs in the page; the attribute checks run here. If either
    says no — or if asking throws — the element is not pressed. A guard that
    fails open is not a guard.
    """
    try:
        if not el.evaluate(_SAFE_TO_CLICK_JS):
            return False
        if (el.get_attribute("type") or "").lower() in _NEVER_CLICK_TYPES:
            return False
        if el.get_attribute("href") is not None:
            return False
    except Exception:
        return False
    return True


def _has_lead_form(forms) -> bool:
    """A form a visitor can type into. Nav search boxes and stubs do not count."""
    for form in forms or []:
        typable = [
            f for f in (form.get("fields") or [])
            if f.get("type") not in ("hidden", "submit", "button", "image", "reset")
        ]
        if typable:
            return True
    return False


def _form_signature(form) -> tuple:
    """Identity of a form across two collections of the same page."""
    return (
        form.get("identifier") or "",
        form.get("label") or "",
        form.get("action_url") or "",
        form.get("field_count"),
        bool(form.get("synthetic")),
    )


_SKIP_FRAME_URLS = ("about:blank", "about:srcdoc", "")


def _collect_all_forms(page) -> list:
    """Every form in every frame.

    HubSpot, Typeform and Jotform all render their form inside an iframe, so a
    main-frame-only sweep found none of them. Playwright can evaluate inside a
    cross-origin frame; plain page JS cannot. A frame that refuses is skipped,
    not fatal.
    """
    forms = []
    for frame in page.frames:
        if frame.url in _SKIP_FRAME_URLS:
            continue
        try:
            found = (frame.evaluate(_COLLECT_FORMS_JS) or []) + \
                    (frame.evaluate(_COLLECT_FORMLESS_JS) or [])
        except Exception:
            continue          # detached, or a frame we may not touch
        if frame is not page.main_frame:
            for form in found:
                form["frame_url"] = frame.url
        forms.extend(found)
    return forms


def _reveal_forms(page) -> list:
    """Press CTAs that may build a form, and return only the forms that APPEAR.

    Forms already on the page are excluded: the caller adds this to its own list
    and would otherwise count them twice, and stamp them as "revealed by" a
    button that had nothing to do with them.
    """
    revealed = []
    try:
        candidates = page.query_selector_all(_REVEAL_SELECTOR)
        already = {_form_signature(f) for f in _collect_all_forms(page)}
    except Exception:
        return revealed
    if not candidates:
        return revealed

    page.route("**/*", _block_non_get)
    page.on("dialog", lambda d: d.dismiss())
    page.on("popup", lambda p: p.close())

    deadline = time.monotonic() + REVEAL_BUDGET_SECONDS
    clicks = 0
    try:
        while clicks < MAX_REVEAL_CLICKS and time.monotonic() < deadline:
            # Re-query every round: a click can make the real CTA visible. On a
            # GoHighLevel course page "Join The Next Cohort" lives in a
            # display:none column until a lesson tab is pressed.
            target, text = _next_reveal_target(page)
            if target is None:
                break

            try:
                target.evaluate("(el) => el.setAttribute('data-linkspy-tried', '1')")
                before_fields = _field_count(page)
                target.click(timeout=1500, no_wait_after=True)
                clicks += 1
                # A modal is fetched and built. Polling beats guessing a delay:
                # a fixed 700ms read the DOM before the form existed.
                _wait_for_new_fields(page, before_fields)
                found = _collect_all_forms(page)
            except Exception:
                continue

            fresh = [f for f in found if _form_signature(f) not in already]
            if _has_lead_form(fresh):
                for form in fresh:
                    form["revealed_by"] = text[:60]
                revealed = fresh
                break
    finally:
        try:
            page.unroute("**/*", _block_non_get)
        except Exception:
            pass
    return revealed


FIELD_WAIT_MS = 2500
_FIELD_POLL_MS = 250


def _field_count(page) -> int:
    try:
        return page.evaluate("document.querySelectorAll('input, textarea, select').length")
    except Exception:
        return 0


def _wait_for_new_fields(page, before: int) -> None:
    """Give a modal time to build itself, but never more than it needs."""
    waited = 0
    while waited < FIELD_WAIT_MS:
        page.wait_for_timeout(_FIELD_POLL_MS)
        waited += _FIELD_POLL_MS
        if _field_count(page) > before:
            page.wait_for_timeout(_FIELD_POLL_MS)   # let the rest of it render
            return


def _next_reveal_target(page):
    """The next button worth pressing: a CTA by name, else any safe button.

    A wordlist alone never reaches a CTA that is hidden behind a tab. Both tiers
    pass the same guards — the second is not a relaxation of safety, only of
    which words we recognise.
    """
    try:
        candidates = page.query_selector_all(_REVEAL_SELECTOR)
    except Exception:
        return None, ""

    fallback = None
    for el in candidates:
        try:
            if el.get_attribute("data-linkspy-tried"):
                continue
        except Exception:
            continue
        if not _click_is_safe(el):
            continue
        try:
            text = (el.inner_text() or "").strip()
        except Exception:
            continue
        if not text:
            continue
        if _CTA_TEXT_RE.search(text):
            return el, text
        if fallback is None:
            fallback = (el, text)
    return fallback if fallback else (None, "")


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
        try:
            # Read-only. See _COLLECT_FORMS_JS: nothing here submits a form.
            # Every frame, not just the main one: HubSpot and Typeform render
            # their forms in an iframe. Includes <div>s that behave like forms —
            # most React and page-builder lead captures have no <form> tag.
            forms = _collect_all_forms(page)
            # Still nothing to type into? A CTA may build the form on click.
            if not _has_lead_form(forms):
                forms += _reveal_forms(page)
            signals["forms"] = forms
        except Exception as e:
            print(f"[Forms] inventory failed (non-critical): {type(e).__name__}: {e}")
            signals["forms"] = []
        browser.close()

    soup = BeautifulSoup(html, "lxml")

    # A document-level listener means handlers are delegated (React and friends),
    # so the absence of a listener on a form proves nothing about it.
    signals["delegated"] = bool(soup.find(attrs={"data-js-delegated": True}))

    # Passive tracking/pixel inventory, read from the rendered HTML — the GTM/GA4/
    # Meta snippets are inline scripts in the DOM by now. Never a network call.
    try:
        signals["tracking"] = extract_tracking(soup)
    except Exception as e:
        print(f"[Tracking] inventory failed (non-critical): {type(e).__name__}: {e}")
        signals["tracking"] = {}

    results: list[RawLink] = _collect_links(soup, url)
    results.extend(find_dead_ctas(soup, url))
    results.extend(merge_resources(
        collect_resources(soup, url),
        resources_from_stylesheets(stylesheets, url),
        already_seen={r.url for r in results},
    ))

    # Form actions are just URLs. Hand them to the existing checker rather than
    # building a second one: they are checked, bucketed and diffed like anything
    # else. A GET, never a POST — the audit is observation-only.
    results.extend(form_action_links(
        signals["forms"], url, already_seen={r.url for r in results},
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
