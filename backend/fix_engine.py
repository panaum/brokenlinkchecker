"""
Deterministic fix suggestions.

A client follows these instructions on a live page. A wrong instruction breaks a
real site. So there is no model in this file and there never will be: every
field of a FixSuggestion traces to (a) a hand-authored YAML template and
(b) data the scan actually observed.

The only inference is a fuzzy string match, and it is gated: a proposed value is
offered only above a similarity threshold, is always validated, and is always
labelled as a suggestion the human must confirm.
"""
import html
import os
import re
from functools import lru_cache
from urllib.parse import urlsplit, unquote

import yaml
from rapidfuzz import fuzz, process

from models import FixSuggestion
from redirect_rules import is_safe_url

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "fix_templates")
_CLIENT_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "client_templates")

# ─── Issue taxonomy ──────────────────────────────────────────────────────────
BROKEN_LINK = "broken_link"
DEAD_CTA = "dead_cta"
REDIRECT_CHAIN = "redirect_chain"
MIXED_CONTENT = "mixed_content"
MISSING_ASSET = "missing_asset"
EXTERNAL_DOWN = "external_down"

ISSUE_TYPES = (BROKEN_LINK, DEAD_CTA, REDIRECT_CHAIN, MIXED_CONTENT,
               MISSING_ASSET, EXTERNAL_DOWN)

# Builder name (from detect_builders) -> template slug. Builders that share a
# fix procedure share a template; anything unmapped falls back to generic.
BUILDER_TEMPLATES = {
    "Elementor": "elementor",
    "GoHighLevel": "ghl",
    "ClickFunnels": "clickfunnels",
    "Unbounce": "unbounce",
    "Webflow": "webflow",
    "Squarespace": "squarespace",
    "Kajabi": "kajabi",
    "HubSpot CMS": "hubspot",
    "Shopify": "shopify",
    "Astro": "astro",
    # These are WordPress page builders. Their editors differ; the underlying
    # cause and cure do not.
    "Divi": "wordpress",
    "WPBakery": "wordpress",
    "Beaver Builder": "wordpress",
    "Bricks": "wordpress",
    "Oxygen": "wordpress",
    "Brizy": "wordpress",
    "Gutenberg": "wordpress",
}

GENERIC = "generic"

# A suggested replacement below this similarity is worse than no suggestion:
# it invites a client to point a link somewhere plausible and wrong.
FUZZY_THRESHOLD = 85

# Similarity alone is not enough. "/a" scores 90 against "/about-us" because the
# whole of "/a" appears in it — but proposing "/about-us" for "/a" is nonsense.
# Require the shorter string to be at least half the longer one.
MIN_LENGTH_RATIO = 0.5

MISSING = "(not available)"

# Fragments that are behaviour, not a scroll target — never fuzzy-matched.
_NON_IDENTIFIER = re.compile(r"[^A-Za-z0-9_\-.:]")


# ─── Template loading ────────────────────────────────────────────────────────
@lru_cache(maxsize=None)
def _load(slug: str) -> dict:
    path = os.path.join(_TEMPLATE_DIR, f"{slug}.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def _client_templates() -> dict:
    path = os.path.join(_CLIENT_TEMPLATE_DIR, "emails.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def template_slug(builder: str) -> str:
    return BUILDER_TEMPLATES.get(builder or "", GENERIC)


# Page builders that coexist on one WordPress site. Detecting Elementor AND
# Gutenberg is normal; detecting Elementor AND Shopify is a contradiction.
_WORDPRESS_FAMILY = frozenset({
    "Elementor", "Divi", "WPBakery", "Beaver Builder", "Bricks",
    "Oxygen", "Brizy", "Gutenberg",
})
# Within WordPress, the page builder that owns the editing experience wins.
# Gutenberg is last: nearly every WP site reports it.
_WORDPRESS_PRIORITY = ["Elementor", "Divi", "Bricks", "Oxygen", "Brizy",
                       "Beaver Builder", "WPBakery", "Gutenberg"]


def _stack_of(builder: str) -> str:
    return "WordPress" if builder in _WORDPRESS_FAMILY else builder


def choose_builder(builders) -> str:
    """The single builder whose instructions apply, or "" for generic.

    Detection returns several names. Some combinations are consistent — Elementor
    and Gutenberg both mean one WordPress site. Others contradict each other
    ("Unbounce, Framer"), which means at least one detection is wrong.

    Guessing is not a cosmetic error here: it renders instructions telling a
    client to click through the wrong editor on a live page. A builder with no
    template of its own still counts as evidence of a different stack — it must
    not be ignored simply because we have nothing to say about it.
    """
    detected = [b for b in (builders or []) if b]
    if not detected:
        return ""

    if len({_stack_of(b) for b in detected}) > 1:
        return ""   # contradictory detection — do not guess

    if _stack_of(detected[0]) == "WordPress":
        for builder in _WORDPRESS_PRIORITY:
            if builder in detected:
                return builder
        return ""

    builder = detected[0]
    return builder if builder in BUILDER_TEMPLATES else ""


def available_templates() -> list:
    return sorted({GENERIC, *BUILDER_TEMPLATES.values()})


class _SafeDict(dict):
    """A missing placeholder renders as "(not available)", never a stray brace
    and never a KeyError in front of a client."""

    def __missing__(self, key):
        return MISSING


def render(text: str, context: dict) -> str:
    return str(text).format_map(_SafeDict(context))


def get_template(builder: str, issue_type: str) -> dict:
    """Builder entry if it has one, else the generic entry. Never raises."""
    for slug in (template_slug(builder), GENERIC):
        entry = (_load(slug).get("issues") or {}).get(issue_type)
        if entry:
            return {**entry, "_slug": slug, "_display": _load(slug).get("display_name", slug)}
    raise KeyError(f"no template for issue_type={issue_type!r} in any builder or generic")


# ─── Finding access (works on LinkResult, FindingRecord, or a plain dict) ────
def _get(finding, field, default=None):
    if isinstance(finding, dict):
        return finding.get(field, default)
    return getattr(finding, field, default)


# ─── Classification ──────────────────────────────────────────────────────────
def classify_issue(finding, page_url: str = "") -> str:
    """Which of the six issue types this finding is. Order matters."""
    url = _get(finding, "url", "") or ""
    bucket = _get(finding, "bucket", "") or ""
    resource_type = _get(finding, "resource_type", "anchor") or "anchor"
    is_external = bool(_get(finding, "is_external", False))
    flags = _get(finding, "redirect_flags") or []

    page = page_url or _get(finding, "page_url", "") or ""

    # An https page loading an http asset is blocked by the browser, whatever
    # the status code says — so this outranks "broken".
    if page.startswith("https://") and url.startswith("http://") and resource_type != "anchor":
        return MIXED_CONTENT

    if bucket == "dead_cta":
        return DEAD_CTA

    if bucket == "broken":
        if resource_type != "anchor":
            return MISSING_ASSET
        return EXTERNAL_DOWN if is_external else BROKEN_LINK

    if flags:
        return REDIRECT_CHAIN

    # Nothing actionable; the caller decides whether to skip it.
    return BROKEN_LINK


# ─── Proposed values ─────────────────────────────────────────────────────────
def _redirect_target(finding) -> str:
    chain = _get(finding, "redirect_chain") or []
    if len(chain) < 2:
        return ""
    target = (chain[-1] or {}).get("url", "")
    return target if is_safe_url(target) else ""


def _is_identifier(fragment: str) -> bool:
    return bool(fragment) and not _NON_IDENTIFIER.search(fragment)


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _slug_tokens(value: str) -> str:
    """"/about-us-old" -> "about us old". Comparing words rather than punctuation
    stops "-" and "/" from dominating the score."""
    return " ".join(t for t in _TOKEN_SPLIT.split((value or "").lower()) if t)


def _best_match(query: str, candidates) -> tuple:
    """(candidate, score) above the threshold, or ('', 0).

    Two gates, both necessary:
      similarity  — the strings must actually look alike
      length      — "/a" is 90% similar to "/about-us" because it is contained in
                    it. Proposing "/about-us" for "/a" is nonsense.
    """
    query_tokens = _slug_tokens(query)
    if not query_tokens or not candidates:
        return "", 0

    tokenized = {}
    for candidate in candidates:
        tokens = _slug_tokens(candidate)
        if tokens:
            tokenized.setdefault(tokens, candidate)
    if not tokenized:
        return "", 0

    match = process.extractOne(query_tokens, list(tokenized), scorer=fuzz.WRatio)
    if not match or match[1] < FUZZY_THRESHOLD:
        return "", 0

    matched_tokens = match[0]
    shorter, longer = sorted((len(query_tokens), len(matched_tokens)))
    if longer == 0 or shorter / longer < MIN_LENGTH_RATIO:
        return "", 0

    return tokenized[matched_tokens], int(match[1])


def suggest_fragment(missing: str, candidates) -> tuple:
    """Closest real id on the page to a missing #fragment. ('', 0) if none."""
    missing = unquote(missing or "")
    if not _is_identifier(missing):
        return "", 0
    usable = [c for c in candidates if _is_identifier(c)]
    return _best_match(missing, usable)


def suggest_url(broken: str, candidates) -> tuple:
    """Closest working URL on the site to a 404'd one. ('', 0) if none.

    Compared on path, not on the whole URL: every candidate shares the host, so
    including it inflates every score toward the threshold.
    """
    if not broken or not candidates:
        return "", 0
    safe = [c for c in candidates if is_safe_url(c) and c != broken]
    if not safe:
        return "", 0

    def path_of(u):
        parts = urlsplit(u)
        return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")

    by_path = {}
    for candidate in safe:
        by_path.setdefault(path_of(candidate), candidate)

    match, score = _best_match(path_of(broken), list(by_path))
    return (by_path[match], score) if match else ("", 0)


def _validate_proposed(value: str, issue_type: str) -> str:
    """A proposed value is written into a CSV, a markdown file, and possibly a
    code change. It came from a scanned page. Validate it, always."""
    if not value:
        return ""
    if issue_type == DEAD_CTA and value.startswith("#"):
        return value if _is_identifier(value[1:]) else ""
    return value if is_safe_url(value) else ""


# ─── The engine ──────────────────────────────────────────────────────────────
def build_fix_suggestion(finding, detected_builder: str = "", *,
                         page_url: str = "",
                         page_fragments=(), site_urls=()) -> FixSuggestion:
    """One suggestion for one finding. Deterministic and traceable.

    `page_fragments` are the real element ids on the page; `site_urls` are the
    working URLs found on the site. Both come from the scan, and both are only
    ever used to *propose* a value the human must confirm.
    """
    issue_type = classify_issue(finding, page_url)
    template = get_template(detected_builder, issue_type)

    url = _get(finding, "url", "") or ""
    fragment = _get(finding, "fragment", "") or ""
    redirect_target = _redirect_target(finding)

    proposed, score = "", 0
    if issue_type == REDIRECT_CHAIN:
        proposed, score = redirect_target, 100 if redirect_target else 0
    elif issue_type == DEAD_CTA and fragment:
        match, score = suggest_fragment(fragment, page_fragments)
        proposed = f"#{match}" if match else ""
    elif issue_type in (BROKEN_LINK, EXTERNAL_DOWN):
        if redirect_target:
            # It redirected before it died: that target is evidence, not a guess.
            proposed, score = redirect_target, 100
        else:
            proposed, score = suggest_url(url, site_urls)
    elif issue_type == MIXED_CONTENT:
        https = "https://" + url[len("http://"):]
        proposed, score = (https, 100) if is_safe_url(https) else ("", 0)

    proposed = _validate_proposed(proposed, issue_type)
    if not proposed:
        score = 0

    # One sentence, phrased for whichever case we are in. Templates that said
    # "Suggested replacement: {proposed_value}. Confirm it is right." produced
    # "Suggested replacement: none. Confirm it is right." when there was nothing
    # to suggest — nonsense in front of a client.
    if proposed:
        suggestion_sentence = (
            f"Suggested replacement: {proposed}. Confirm this is correct before you "
            "save it — it was matched by text similarity, not by knowing your intent."
        )
    else:
        suggestion_sentence = (
            "We cannot suggest a replacement for this one: nothing on the site is a "
            "close enough match. Decide the correct destination yourself."
        )

    context = {
        "url": url or MISSING,
        "anchor_text": _get(finding, "anchor_text", "") or "this element",
        "page_url": page_url or _get(finding, "page_url", "") or MISSING,
        "status_code": _get(finding, "status_code") or "an error",
        "resource_type": _get(finding, "resource_type", "anchor") or "asset",
        "fragment": fragment or MISSING,
        "proposed_value": proposed or "none",
        "suggestion_sentence": suggestion_sentence,
        "redirect_target": redirect_target or MISSING,
        "hops": len(_get(finding, "redirect_chain") or []) - 1 or MISSING,
        "builder": template["_display"],
    }

    steps = [render(step, context) for step in template.get("steps", [])]

    # Confidence describes the PROPOSED VALUE, not the instructions. The
    # instructions are always trustworthy; the suggested replacement may not be.
    if not proposed:
        confidence = "low"
    elif score >= 100:
        confidence = "high"
    elif score >= 92:
        confidence = "medium"
    else:
        confidence = "low"

    return FixSuggestion(
        finding_id=_get(finding, "fingerprint", "") or _get(finding, "id", "") or "",
        issue_type=issue_type,
        fix_type=_FIX_TYPES[issue_type],
        proposed_value=proposed or None,
        title=render(template.get("title", ""), context),
        steps=steps,
        instructions="\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)),
        est_time_minutes=int(template.get("est_time_minutes", 10)),
        requires_dev=bool(template.get("requires_dev", False)),
        confidence=confidence,
        match_score=score,
        builder=template["_display"],
        template_source=f"fix_templates/{template['_slug']}.yaml",
    )


_FIX_TYPES = {
    BROKEN_LINK: "replace_href",
    DEAD_CTA: "attach_destination",
    REDIRECT_CHAIN: "collapse_redirect",
    MIXED_CONTENT: "upgrade_to_https",
    MISSING_ASSET: "restore_asset",
    EXTERNAL_DOWN: "review_external_link",
}


# ─── Client-facing messages ──────────────────────────────────────────────────
def render_client_message(finding, *, page_url: str = "", site_url: str = "",
                          eta: str = "within 2 business days",
                          age_phrase: str = "") -> dict:
    """A copy-pasteable message for the client.

    Every interpolated value is HTML-escaped. Anchor text comes from a scanned
    page: `<img src=x onerror=alert(1)>` is a perfectly legal anchor text, and it
    must not survive into an email a human forwards.
    """
    issue_type = classify_issue(finding, page_url)
    template = (_client_templates().get("issues") or {}).get(issue_type)
    if not template:
        raise KeyError(f"no client template for {issue_type!r}")

    chain = _get(finding, "redirect_chain") or []
    context = {
        "anchor_text": html.escape(_get(finding, "anchor_text", "") or "this element"),
        "url": html.escape(_get(finding, "url", "") or MISSING),
        "page_url": html.escape(page_url or MISSING),
        "site_url": html.escape(site_url or MISSING),
        "status_code": html.escape(str(_get(finding, "status_code") or "an error")),
        "resource_type": html.escape(_get(finding, "resource_type", "asset") or "asset"),
        "redirect_target": html.escape(_redirect_target(finding) or MISSING),
        "hops": max(len(chain) - 1, 0) or MISSING,
        "eta": html.escape(eta),
        "age_phrase": html.escape(age_phrase),
    }
    return {
        "issue_type": issue_type,
        "subject": render(template["subject"], context),
        "body": render(template["body"], context).strip(),
    }


def render_report_summary(*, site_url: str, summary_line: str, new_count: int) -> dict:
    template = _client_templates()["report_summary"]
    context = {
        "site_url": html.escape(site_url or MISSING),
        "summary_line": html.escape(summary_line or ""),
        "new_count": int(new_count),
    }
    return {
        "subject": render(template["subject"], context),
        "body": render(template["body"], context).strip(),
    }
