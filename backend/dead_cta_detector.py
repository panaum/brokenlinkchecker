"""
Dead-CTA detection with false-positive suppression.

The naive approach (flag any anchor/button whose static href/onclick goes
nowhere) mislabels working JS-driven UI — menu toggles, tabs, carousel arrows,
accordions, modal triggers — as "Dead CTA". This module layers several
suppression checks (runtime-listener proof, declarative interactivity, widget
context, page-builder idioms) on top of the detection rules so only genuinely
dead calls-to-action are flagged.

Public API:
    find_dead_ctas(soup, url) -> list[RawLink]
    detect_builders(soup)     -> list[dict]
    LISTENER_PROBE_JS         -> str   (Playwright init script)
"""

import re
from urllib.parse import urlparse, unquote
from models import RawLink


# ─────────────────────────────────────────────────────────────────────────────
# Playwright init script: proves an element (or the document, for delegated
# React-style handlers) has a runtime click listener by stamping a data attr.
# ─────────────────────────────────────────────────────────────────────────────
LISTENER_PROBE_JS = r"""
(function () {
  try {
    // 'submit' is here so a <form> whose handler is attached in JS can be
    // observed. This RECORDS that a listener was registered; it never fires
    // one. Nothing in this probe submits anything.
    var CLICKY = ['click', 'pointerdown', 'pointerup', 'mousedown',
                  'mouseup', 'touchstart', 'touchend', 'keydown', 'submit'];
    var orig = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function (type, listener, options) {
      try {
        if (CLICKY.indexOf(type) !== -1) {
          if (this instanceof Element) {
            this.setAttribute('data-js-listener', '1');
          } else if (this === document || this === window ||
                     this === (document && document.documentElement)) {
            if (document && document.documentElement) {
              document.documentElement.setAttribute('data-js-delegated', '1');
            }
          }
        }
      } catch (e) {}
      return orig.call(this, type, listener, options);
    };
  } catch (e) {}
})();
"""


# ─── Dead href values ────────────────────────────────────────────────────────
DEAD_HREF_LITERALS = {"", "#", "#0", "#!", "#null", "#undefined"}

# ─── Suppression: declarative interactivity ──────────────────────────────────
DECLARATIVE_ATTRS = {
    "aria-controls", "aria-expanded", "aria-haspopup",
    "aria-pressed", "aria-selected", "aria-modal",
}

DECLARATIVE_PREFIXES = (
    "data-toggle", "data-bs-", "data-target", "data-open", "data-close",
    "data-dismiss", "data-modal", "data-popup", "data-lightbox",
    "data-fancybox", "data-featherlight", "data-remodal", "data-micromodal",
    "data-izimodal", "data-elementor", "data-gtm", "data-ga", "data-track",
    "data-analytics", "data-action", "data-click", "data-slide", "data-tab",
    "data-accordion", "data-collapse", "data-dropdown", "data-menu",
    "data-w-id", "data-ix", "data-scroll", "data-video", "data-vimeo",
    "data-youtube", "data-src", "data-href", "data-url", "data-link",
    "data-form", "data-step", "data-cf-", "data-ghl", "data-funnel",
    "data-wf-", "data-js-listener",
)

# ─── Suppression: interactive roles ──────────────────────────────────────────
INTERACTIVE_ROLES = {
    "tab", "menuitem", "menuitemcheckbox", "menuitemradio",
    "option", "switch", "combobox", "presentation", "none",
}

# ─── Suppression: widget-context class/id keywords ───────────────────────────
# NOTE: matched against a class+id blob with the substring "table" stripped
# first (so "tab" never matches "pricing-table"); "theme-" carries the hyphen
# so body classes like et_divi_theme / kajabi-theme do NOT suppress the page.
WIDGET_KEYWORDS = [
    "swiper", "slick", "splide", "owl-", "carousel", "slider", "flickity",
    "glide", "accordion", "collaps", "tab", "toggle", "dropdown", "menu",
    "nav", "burger", "hamburger", "modal", "popup", "lightbox", "dialog",
    "drawer", "offcanvas", "close", "dismiss", "cookie", "consent", "gdpr",
    "search", "scroll", "back-to-top", "backtotop", "play", "video", "mute",
    "pause", "expand", "filter", "sort", "pagination", "prev", "next",
    "arrow", "dot", "indicator", "bullet", "share", "social", "copy",
    "print", "clipboard", "theme-", "dark-mode", "color-scheme", "lang",
    "login", "log-in", "signin", "sign-in", "account", "skip", "show-more",
    "load-more", "read-more", "readmore", "qty", "quantity", "stepper",
    "zoom", "gallery", "thumb", "faq",
]

# ─── Broken in-page anchor: fragment prefixes that are functional, not links ──
FUNCTIONAL_FRAGMENT_PREFIXES = [
    "elementor-action", "popup", "open-popup", "open-", "submit-form",
    "next-step", "show-hide", "modal", "lightbox", "scroll-",
]

# ─── Placeholder markers (AI/template leftovers), matched on host + path ─────
PLACEHOLDER_MARKERS = [
    "example.com", "example.org", "yourdomain.", "yoursite.",
    "your-domain.", "yourwebsite.", "placeholder.", "yourlink.",
    "/yourhandle",
]

# ─── Confidence: CTA signals ─────────────────────────────────────────────────
CTA_CLASS_KEYWORDS = [
    "btn", "button", "cta", "call-to-action", "signup", "sign-up", "register",
    "get-started", "getstarted", "get_started", "subscribe", "download",
    "buy-now", "buynow", "order-now", "ordernow", "free-trial", "freetrial",
    "book-demo", "bookdemo", "contact-us", "contactus", "start-free",
    "try-free", "get-quote", "request-demo",
]

CTA_VERBS = [
    "buy", "order", "sign up", "get started", "start", "try", "download",
    "subscribe", "book", "request", "demo", "quote", "contact", "join",
    "claim", "enroll", "apply", "schedule", "register", "purchase",
    "get a", "sign-up", "get started free",
]

# ─── SPA page-level markers ──────────────────────────────────────────────────
SPA_MARKERS = [
    "data-reactroot", "__next_data__", "__nuxt", "ng-version",
    "data-v-app", "data-svelte", "q:container", "data-js-delegated",
]
SPA_ROOT_IDS = ("root", "app", "__next", "___gatsby")


def bucket_for_confidence(confidence: str) -> str:
    """high/medium dead-CTA candidates are actionable; low ones are a soft warning."""
    return "unverifiable" if confidence == "low" else "dead_cta"


# ─────────────────────────────────────────────────────────────────────────────
# Page-builder profiles. A matched profile merges its widget_hints /
# data_prefixes / functional_fragments into suppression, may force SPA-level
# low confidence, and has its name appended to every flag's reason.
#
# Detect markers must be *product fingerprints*, not vendor names. A bare name
# like "shopify" or "webflow" matches any page that merely mentions the vendor —
# a customer-logo SVG (aria-label="webflow"), a theme called "astro-shopify", a
# link to squarespace.com. That misattributes the builder in the client-facing
# report AND merges that builder's widget hints into suppression, which can hide
# genuinely dead CTAs. Prefer CDN hosts, framework-emitted class/data prefixes,
# and `content="<name>` for meta-generator-only builders.
# ─────────────────────────────────────────────────────────────────────────────
def _compile_marker(marker: str):
    """
    Compile a detect marker to a regex over the lowercased page HTML.

    A marker that begins with a word character must start at a token boundary,
    or it matches inside an unrelated identifier: "ct-section" (Oxygen) was
    matching "use-produ|ct-section-visibility.js" on a Shopify store. Markers
    that begin with punctuation ("/cdn/shop/", ".webflow.io") get no guard —
    they are routinely preceded by a word character, as in "…allbirds.com/cdn/shop/".
    """
    head = marker[:1]
    guard = r"(?<![a-z0-9_])" if (head.isalnum() or head == "_") else ""
    return re.compile(guard + re.escape(marker))


def _profile(name, detect, widget_hints=None, data_prefixes=None,
             functional_fragments=None, spa=False):
    return {
        "name": name,
        "detect": detect,
        "detect_res": [_compile_marker(m) for m in detect],
        "widget_hints": widget_hints or [],
        "data_prefixes": data_prefixes or [],
        "functional_fragments": functional_fragments or [],
        "spa": spa,
    }


BUILDER_PROFILES = [
    _profile("Elementor", ["elementor"],
             widget_hints=["elementor-tab", "elementor-toggle", "elementor-swiper", "dialog-"],
             data_prefixes=["data-e-"], functional_fragments=["elementor-action"]),
    _profile("Divi", ["et_pb_", "et-db"],
             widget_hints=["et_pb_toggle", "et_pb_tab", "et_pb_video_overlay", "mfp-", "et_mobile"]),
    _profile("WPBakery", ["js_composer", "vc_row"],
             widget_hints=["vc_toggle", "vc_tta", "prettyphoto"]),
    _profile("Beaver Builder", ["fl-builder"],
             widget_hints=["fl-menu", "fl-slider", "fl-tabs", "fl-accordion"]),
    _profile("Bricks", ["brxe-"],
             widget_hints=["brxe-nav", "brxe-accordion", "brxe-tabs", "brxe-slider"]),
    _profile("Oxygen", ["ct-section", "oxygen-body"],
             widget_hints=["ct-slider", "oxy-tab", "oxy-toggle", "oxy-nav"]),
    _profile("Brizy", ["brz-"],
             widget_hints=["brz-menu", "brz-tabs", "brz-accordion", "brz-slider"],
             data_prefixes=["data-brz"]),
    _profile("Gutenberg", ["wp-block-"],
             widget_hints=["wp-block-navigation", "wp-block-details"]),
    _profile("Webflow", ["data-wf-page", "data-wf-site", "data-wf-domain",
                         "website-files.com", ".webflow.io", "webflow.js"],
             widget_hints=["w-nav", "w-dropdown", "w-slider", "w-tab", "w-lightbox"]),
    _profile("Wix", ["parastorage", "wixstatic"], spa=True),
    _profile("Squarespace", ["squarespace-cdn", "static1.squarespace", "sqs-"],
             widget_hints=["sqs-block-accordion", "sqs-popup", "sqs-pill",
                           "header-burger", "sqs-announcement"]),
    # NOT the bare word "unbounce": an agency that *builds* Unbounce pages says
    # so in its copy ("...managing 50+ unbounce pages..."), and its own site is
    # not Unbounce. Detecting it there renders the wrong fix instructions.
    _profile("Unbounce", ["lp-pom", "ub-emb", "unbouncepages.com", "ubembed.com"],
             widget_hints=["ub-emb"], data_prefixes=["data-ub"]),
    _profile("ClickFunnels", ["clickfunnels", "containerwrapper", "data-page-element"],
             widget_hints=["elmodal", "eltimer", "elvideo"],
             data_prefixes=["data-show-", "data-de-", "data-page-element"],
             functional_fragments=["submit-form", "open-popup", "next-step",
                                   "show-hide", "back-step", "order-bump"]),
    _profile("GoHighLevel", ["leadconnectorhq", "highlevel", "msgsndr", "gohighlevel"],
             widget_hints=["hl_", "c-modal", "c-timer"],
             data_prefixes=["data-hl"], functional_fragments=["popup"]),
    _profile("Leadpages", ["leadpages", "lpages.co"], data_prefixes=["data-leadbox"]),
    _profile("Instapage", ["instapage-", "cdn.instapage"], functional_fragments=["element-"]),
    _profile("Kajabi", ["kajabi-cdn", "kajabi-theme", "kjb-"],
             widget_hints=["kjb-slider", "offcanvas", "sales-cta"],
             data_prefixes=["data-kjb-checkout"]),
    _profile("HubSpot CMS", ["hs-scripts", "hs_cos", "hubspotusercontent"],
             widget_hints=["hs-menu", "hs-search", "hs-accordion"],
             data_prefixes=["data-hs-"]),
    _profile("Shopify", ["cdn.shopify", "myshopify.com", "/cdn/shop/",
                         "shopify-features", "shopify-section", "shopify-payment"],
             widget_hints=["shopify-payment", "cart-drawer", "product-form",
                           "quick-add", "predictive-search", "deferred-media"]),
    # NOT bare "framer-": it matches an ordinary link like
    # href="/framer-development-agency/". Framer's own markup emits
    # data-framer-* attributes and loads assets from framerusercontent.com.
    _profile("Framer", ["framerusercontent", "data-framer-", "__framer"], spa=True),
    _profile("Duda", ["irp.cdn-website.com", "dudamobile", "dmalbum", 'content="duda'],
             widget_hints=["dmnav", "dmmenu"]),
    _profile("Carrd", ['content="carrd', "carrd.co"], spa=True),
    _profile("Astro", ['content="astro', "astro-island"]),
    # Static-site generators: identified solely by their meta generator tag.
    _profile("Hugo", ['content="hugo']),
    _profile("Jekyll", ['content="jekyll']),
    _profile("Eleventy", ['content="eleventy']),
]


# ─────────────────────────────────────────────────────────────────────────────
# Small DOM helpers
# ─────────────────────────────────────────────────────────────────────────────
def _classes(tag) -> str:
    c = tag.get("class")
    if not c:
        return ""
    if isinstance(c, str):
        return c.lower()
    return " ".join(c).lower()


def _widget_blob(tag) -> str:
    """class + id blob, with 'table' stripped so 'tab' != 'pricing-table'."""
    blob = _classes(tag) + " " + (tag.get("id") or "").lower()
    return blob.replace("table", "")


def _real_onclick(onclick: str) -> bool:
    """True if onclick has real code after stripping no-op tokens."""
    if not onclick:
        return False
    s = onclick.lower()
    for tok in (
        "event.preventdefault()", "e.preventdefault()", "preventdefault()",
        "void(0)", "void 0", "return false", "preventdefault",
        "javascript:", "return", "false",
    ):
        s = s.replace(tok, "")
    s = s.replace(";", "").strip()
    return ("(" in s) or ("=" in s) or ("location" in s)


def _in_astro_island(tag) -> bool:
    for parent in tag.parents:
        if getattr(parent, "name", None) in ("astro-island", "astro-slot"):
            return True
    return False


def _has_cta_signal(tag) -> bool:
    blob = _classes(tag)
    if any(kw in blob for kw in CTA_CLASS_KEYWORDS):
        return True
    text = (tag.get_text(strip=True) or "").lower()
    return any(v in text for v in CTA_VERBS)


# ─────────────────────────────────────────────────────────────────────────────
# Builder detection
# ─────────────────────────────────────────────────────────────────────────────
def detect_builders(soup) -> list:
    html = str(soup).lower()[:300000]
    matched = []
    for profile in BUILDER_PROFILES:
        if any(rx.search(html) for rx in profile["detect_res"]):
            matched.append(profile)
    return matched


def fragment_targets(soup) -> set:
    """Every in-page anchor destination: element ids plus legacy <a name="…">."""
    targets = set()
    for el in soup.find_all(attrs={"id": True}):
        v = el.get("id")
        if v:
            targets.add(v)
            targets.add(v.lower())
    for el in soup.find_all("a", attrs={"name": True}):
        v = el.get("name")
        if v:
            targets.add(v)
            targets.add(v.lower())
    return targets


def is_functional_fragment(fragment: str, extra_prefixes=()) -> bool:
    """True for fragments that drive behaviour rather than scroll to a target."""
    f = fragment.lower()
    if f == "top":  # implicit browser target — always valid
        return True
    prefixes = tuple(FUNCTIONAL_FRAGMENT_PREFIXES) + tuple(extra_prefixes)
    return any(f.startswith(p) for p in prefixes)


def _detect_spa(soup) -> bool:
    head = str(soup)[:4000].lower()
    if any(marker in head for marker in SPA_MARKERS):
        return True
    for root_id in SPA_ROOT_IDS:
        if soup.find(id=root_id) is not None:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Suppression
# ─────────────────────────────────────────────────────────────────────────────
def _is_suppressed(tag, widget_kws, data_prefixes) -> bool:
    # 1. Runtime listener proof
    if tag.get("data-js-listener"):
        return True

    # 2. Real inline onclick
    if _real_onclick(tag.get("onclick", "") or ""):
        return True

    # 3. Declarative interactivity attributes / prefixes
    for attr in tag.attrs:
        a = attr.lower()
        if a in DECLARATIVE_ATTRS:
            return True
        if a.startswith(data_prefixes):
            return True

    # 4. Interactive role
    role = (tag.get("role") or "").lower()
    if role in INTERACTIVE_ROLES:
        return True

    # 5. Widget context (element + up to 3 ancestors)
    node = tag
    for _ in range(4):
        if node is None or not getattr(node, "attrs", None):
            break
        blob = _widget_blob(node)
        if any(kw in blob for kw in widget_kws):
            return True
        node = node.parent
    # ...or anywhere inside <nav>/<header>
    for parent in tag.parents:
        if getattr(parent, "name", None) in ("nav", "header"):
            return True

    # 6. Dropdown parent: <li> directly containing a nested <ul>/<ol>
    parent = tag.parent
    if getattr(parent, "name", None) == "li":
        if parent.find_all(("ul", "ol"), recursive=False):
            return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# href helpers
# ─────────────────────────────────────────────────────────────────────────────
def _is_dead_href(href: str) -> bool:
    h = href.strip().lower()
    if h in DEAD_HREF_LITERALS:
        return True
    if h.startswith("javascript:"):
        rest = h[len("javascript:"):].replace(";", "").replace(" ", "").strip()
        return rest == "" or rest == "null" or rest == "returnfalse" or rest.startswith("void")
    return False


def _placeholder_host(href: str) -> bool:
    """Absolute href whose host *or* path carries a template placeholder marker."""
    h = href.strip().lower()
    if not h.startswith(("http://", "https://")):
        return False
    parsed = urlparse(h)
    target = parsed.netloc + parsed.path
    return any(ph in target for ph in PLACEHOLDER_MARKERS)


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def find_dead_ctas(soup, url: str) -> list:
    builders = detect_builders(soup)

    widget_kws = list(WIDGET_KEYWORDS)
    data_prefixes = list(DECLARATIVE_PREFIXES)
    fragment_prefixes = list(FUNCTIONAL_FRAGMENT_PREFIXES)
    builder_spa = False
    builder_names = []
    for b in builders:
        widget_kws += [w.lower() for w in b["widget_hints"]]
        data_prefixes += [p.lower() for p in b["data_prefixes"]]
        fragment_prefixes += [f.lower() for f in b["functional_fragments"]]
        builder_spa = builder_spa or b["spa"]
        builder_names.append(b["name"])
    data_prefixes = tuple(data_prefixes)

    is_spa = _detect_spa(soup) or builder_spa
    builder_suffix = ""
    if builder_names:
        builder_suffix = " · builder: " + ", ".join(builder_names)

    ids = fragment_targets(soup)

    results: list = []
    seen: set = set()

    def confidence(tag, base="medium"):
        if is_spa or _in_astro_island(tag):
            return "low"
        if _has_cta_signal(tag):
            return "high"
        return base

    def emit(kind, tag, reason, conf):
        anchor = (tag.get_text(strip=True) or "")[:80]
        href = (tag.get("href") or "")
        key = (kind, anchor, href)
        if key in seen:
            return
        seen.add(key)
        results.append(RawLink(
            url=url,
            source_element=tag.name,
            anchor_text=anchor or "[no text]",
            category="Dead CTA",
            is_external=False,
            priority="medium",
            confidence=conf,
            reason=reason + builder_suffix,
            bucket=bucket_for_confidence(conf),
            link_kind="dead_cta",
        ))

    # ── Anchors ──────────────────────────────────────────────────────────────
    for tag in soup.find_all("a"):
        href = (tag.get("href") or "").strip()

        if _is_dead_href(href):
            if _is_suppressed(tag, widget_kws, data_prefixes):
                continue
            emit("anchor", tag, "Anchor href goes nowhere", confidence(tag))
            continue

        if _placeholder_host(href):
            # Always high confidence, even on an SPA or inside a hydration
            # island: those degrade a *handler* inference, but a link pointing
            # at example.com is a content defect that no amount of hydration
            # fixes. Never suppressed for the same reason.
            emit("placeholder", tag, "Placeholder link never wired up", "high")
            continue

        if href.startswith("#") and len(href) > 1:
            frag = unquote(href[1:])
            fl = frag.lower()
            if fl == "top":
                continue
            if any(fl.startswith(pfx) for pfx in fragment_prefixes):
                continue
            if frag in ids or fl in ids:
                continue
            if _is_suppressed(tag, widget_kws, data_prefixes):
                continue
            emit("fragment", tag,
                 f"In-page anchor target #{frag} not found on page",
                 confidence(tag))
            continue

    # ── <button> ─────────────────────────────────────────────────────────────
    for tag in soup.find_all("button"):
        btype = (tag.get("type") or "").lower()
        if btype in ("submit", "reset"):
            continue
        if btype == "":
            # No type attribute inside a <form> = implicit submit (HTML spec).
            in_form = any(getattr(p, "name", None) == "form" for p in tag.parents)
            if in_form:
                continue
        if _is_suppressed(tag, widget_kws, data_prefixes):
            continue
        emit("button", tag,
             "Button has no static handler; a listener may attach at runtime",
             confidence(tag))

    # ── div / span / li with role="button" ──────────────────────────────────
    for tag in soup.find_all(["div", "span", "li"]):
        if (tag.get("role") or "").lower() != "button":
            continue
        text = tag.get_text(strip=True) or ""
        if len(text) > 50:
            continue
        if _is_suppressed(tag, widget_kws, data_prefixes):
            continue
        emit("role-button", tag,
             "Element with role=button has no detected handler",
             confidence(tag, base="low"))

    return results
