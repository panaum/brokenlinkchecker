"""
Fix engine.

A client follows these instructions on a live page, so the bar is: every field
traces to a hand-authored template plus data the scan observed. Nothing is
generated, nothing is guessed above a threshold, and no attacker-controlled
value reaches a spreadsheet, a markdown file, or an email unescaped.
"""
import pathlib

import pytest

import fix_engine
from fix_engine import (
    BROKEN_LINK,
    DEAD_CTA,
    EXTERNAL_DOWN,
    FUZZY_THRESHOLD,
    ISSUE_TYPES,
    MISSING_ASSET,
    MIXED_CONTENT,
    REDIRECT_CHAIN,
    available_templates,
    build_fix_suggestion,
    choose_builder,
    classify_issue,
    get_template,
    render_client_message,
    render_report_summary,
    suggest_fragment,
    suggest_url,
    template_slug,
)


TEMPLATE_DIR = pathlib.Path(fix_engine._TEMPLATE_DIR)


def _finding(**over) -> dict:
    base = {
        "fingerprint": "fp1", "url": "https://acme.test/gone", "anchor_text": "Buy Now",
        "bucket": "broken", "resource_type": "anchor", "is_external": False,
        "status_code": 404, "fragment": "", "redirect_chain": [], "redirect_flags": [],
    }
    base.update(over)
    return base


# ─── the templates themselves ────────────────────────────────────────────────
def test_every_template_file_is_marked_as_a_draft():
    """The marker is how a human finds what still needs verifying."""
    for path in TEMPLATE_DIR.glob("*.yaml"):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert "DRAFT" in first and "human review" in first, path.name


def test_every_expected_builder_has_a_template():
    expected = {"generic", "elementor", "ghl", "clickfunnels", "unbounce",
                "wordpress", "squarespace", "webflow", "kajabi", "hubspot",
                "shopify", "astro"}
    on_disk = {p.stem for p in TEMPLATE_DIR.glob("*.yaml")}
    assert expected <= on_disk, expected - on_disk


@pytest.mark.parametrize("slug", sorted(
    {"generic", "elementor", "ghl", "clickfunnels", "unbounce", "wordpress",
     "squarespace", "webflow", "kajabi", "hubspot", "shopify", "astro"}))
@pytest.mark.parametrize("issue_type", ISSUE_TYPES)
def test_every_builder_x_issue_has_a_complete_entry(slug, issue_type):
    entry = (fix_engine._load(slug).get("issues") or {}).get(issue_type)
    assert entry, f"{slug} is missing {issue_type}"
    assert entry["issue_type"] == issue_type
    assert entry["title"]
    assert entry["steps"] and all(isinstance(s, str) and s.strip() for s in entry["steps"])
    assert isinstance(entry["est_time_minutes"], int)
    assert isinstance(entry["requires_dev"], bool)


@pytest.mark.parametrize("builder", sorted(fix_engine.BUILDER_TEMPLATES) + ["", "Unknown Builder"])
@pytest.mark.parametrize("issue_type", ISSUE_TYPES)
def test_every_builder_x_issue_renders_without_keyerror_or_stray_braces(builder, issue_type):
    """A leftover "{proposed_value}" in front of a client is unacceptable."""
    template = get_template(builder, issue_type)
    finding = _finding(
        bucket="dead_cta" if issue_type == DEAD_CTA else "broken",
        resource_type="script" if issue_type == MISSING_ASSET else "anchor",
        is_external=(issue_type == EXTERNAL_DOWN),
        url="http://acme.test/a.js" if issue_type == MIXED_CONTENT else "https://acme.test/gone",
        redirect_chain=(
            [{"url": "https://acme.test/a", "status": 301},
             {"url": "https://acme.test/b", "status": 200}]
            if issue_type == REDIRECT_CHAIN else []
        ),
        redirect_flags=["long_chain"] if issue_type == REDIRECT_CHAIN else [],
    )
    fix = build_fix_suggestion(finding, builder, page_url="https://acme.test/page")

    rendered = fix.title + "\n" + "\n".join(fix.steps)
    assert "{" not in rendered and "}" not in rendered, rendered
    assert fix.steps
    assert fix.template_source.startswith("fix_templates/")


def test_unknown_builder_falls_back_to_generic():
    assert template_slug("Nonexistent") == "generic"
    assert get_template("Nonexistent", BROKEN_LINK)["_slug"] == "generic"


def test_wordpress_builders_share_the_wordpress_template():
    for builder in ("Divi", "WPBakery", "Bricks", "Oxygen", "Brizy", "Gutenberg"):
        assert template_slug(builder) == "wordpress"


def test_available_templates_lists_generic():
    assert "generic" in available_templates()


# ─── classification ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("finding,page,expected", [
    (_finding(), "", BROKEN_LINK),
    (_finding(is_external=True), "", EXTERNAL_DOWN),
    (_finding(resource_type="script"), "", MISSING_ASSET),
    (_finding(bucket="dead_cta"), "", DEAD_CTA),
    (_finding(bucket="ok", redirect_flags=["long_chain"]), "", REDIRECT_CHAIN),
    (_finding(url="http://acme.test/a.js", resource_type="script"),
     "https://acme.test/p", MIXED_CONTENT),
])
def test_classify_issue(finding, page, expected):
    assert classify_issue(finding, page) == expected


def test_mixed_content_outranks_broken():
    """A blocked http asset on an https page is mixed content whatever its status."""
    f = _finding(url="http://acme.test/a.js", resource_type="script", bucket="broken")
    assert classify_issue(f, "https://acme.test/p") == MIXED_CONTENT


def test_an_http_anchor_on_an_https_page_is_not_mixed_content():
    """Browsers block sub-resources, not navigation. A plain link is fine."""
    f = _finding(url="http://other.test/page", resource_type="anchor", bucket="ok")
    assert classify_issue(f, "https://acme.test/p") != MIXED_CONTENT


# ─── fuzzy matching ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("missing,ids,expected", [
    ("pricing", ["plans", "pricing-table", "contact"], "pricing-table"),
    ("team", ["our-team", "contact", "faq"], "our-team"),
    ("testimonials", ["testimonial", "features"], "testimonial"),
])
def test_suggest_fragment_hits_known_pairs(missing, ids, expected):
    match, score = suggest_fragment(missing, ids)
    assert match == expected
    assert score >= FUZZY_THRESHOLD


def test_suggest_fragment_refuses_a_weak_match():
    """A plausible-but-wrong anchor sends the client to the wrong section."""
    match, score = suggest_fragment("pricing", ["about-the-founder", "careers"])
    assert match == "" and score == 0


def test_suggest_fragment_ignores_non_identifier_fragments():
    assert suggest_fragment("url=http%3A%2F%2Fx", ["url"]) == ("", 0)
    assert suggest_fragment("!/route", ["route"]) == ("", 0)


def test_suggest_fragment_with_no_candidates():
    assert suggest_fragment("pricing", []) == ("", 0)


def test_suggest_url_matches_on_path_not_host():
    broken = "https://acme.test/about-us-old"
    match, score = suggest_url(broken, ["https://acme.test/about-us",
                                        "https://acme.test/contact"])
    assert match == "https://acme.test/about-us"
    assert score >= FUZZY_THRESHOLD


def test_suggest_url_refuses_a_weak_match():
    match, _ = suggest_url("https://acme.test/pricing", ["https://acme.test/blog/2019/xyz"])
    assert match == ""


def test_suggest_url_never_proposes_an_unsafe_candidate():
    match, _ = suggest_url("https://acme.test/pricing",
                           ["javascript:alert(1)", 'https://acme.test/"pricing'])
    assert match == ""


def test_suggest_url_never_proposes_the_broken_url_itself():
    assert suggest_url("https://acme.test/x", ["https://acme.test/x"]) == ("", 0)


@pytest.mark.parametrize("broken,candidate", [
    ("https://acme.test/about-us-old", "https://acme.test/about-us"),
    ("https://acme.test/contact-us", "https://acme.test/contact"),
    ("https://acme.test/pricing", "https://acme.test/pricing-2"),
    ("https://acme.test/our-team", "https://acme.test/team"),
])
def test_suggest_url_catches_real_renames(broken, candidate):
    match, score = suggest_url(broken, [candidate, "https://acme.test/blog"])
    assert match == candidate
    assert score >= FUZZY_THRESHOLD


def test_a_one_character_path_never_proposes_a_long_one():
    """"/a" scores 90% against "/about-us" purely because it is contained in it.
    Similarity alone is not enough; the length guard is what stops this."""
    match, _ = suggest_url("https://acme.test/a", ["https://acme.test/about-us"])
    assert match == ""


def test_a_short_fragment_never_proposes_a_long_one():
    assert suggest_fragment("a", ["about-the-company"]) == ("", 0)


# ─── proposed values ─────────────────────────────────────────────────────────
def test_redirect_target_is_evidence_not_a_guess():
    f = _finding(redirect_chain=[{"url": "https://acme.test/old", "status": 301},
                                 {"url": "https://acme.test/new", "status": 200}],
                 redirect_flags=["long_chain"], bucket="ok")
    fix = build_fix_suggestion(f, "Elementor", page_url="https://acme.test/p")
    assert fix.issue_type == REDIRECT_CHAIN
    assert fix.proposed_value == "https://acme.test/new"
    assert fix.confidence == "high"


def test_a_broken_link_that_redirected_before_dying_proposes_that_target():
    f = _finding(redirect_chain=[{"url": "https://acme.test/gone", "status": 301},
                                 {"url": "https://acme.test/final", "status": 404}])
    fix = build_fix_suggestion(f, "", page_url="https://acme.test/p")
    assert fix.proposed_value == "https://acme.test/final"


def test_mixed_content_proposes_the_https_form():
    f = _finding(url="http://acme.test/a.js", resource_type="script")
    fix = build_fix_suggestion(f, "", page_url="https://acme.test/p")
    assert fix.issue_type == MIXED_CONTENT
    assert fix.proposed_value == "https://acme.test/a.js"


def test_no_proposal_means_low_confidence_and_a_human_decision():
    fix = build_fix_suggestion(_finding(), "", page_url="https://acme.test/p")
    assert fix.proposed_value is None
    assert fix.confidence == "low"
    assert "human decision" in " ".join(fix.steps).lower() or "confirm" in " ".join(fix.steps).lower()


@pytest.mark.parametrize("malicious", [
    "javascript:alert(1)",
    "data:text/html,<script>",
    'https://acme.test/"onload=x',
    "https://acme.test/a\nRedirect 301 /x /evil",
    "https://good.test@evil.test/",
])
def test_a_malicious_candidate_never_becomes_a_proposed_value(malicious):
    f = _finding(redirect_chain=[{"url": "https://acme.test/gone", "status": 301},
                                 {"url": malicious, "status": 200}],
                 redirect_flags=["long_chain"], bucket="ok")
    fix = build_fix_suggestion(f, "", page_url="https://acme.test/p")
    assert fix.proposed_value is None


def test_dead_cta_fragment_proposal_must_be_an_identifier():
    f = _finding(bucket="dead_cta", fragment="pricing")
    fix = build_fix_suggestion(f, "", page_url="https://acme.test/p",
                               page_fragments=["pricing-table"])
    assert fix.proposed_value == "#pricing-table"


def test_suggestion_records_its_template_source():
    fix = build_fix_suggestion(_finding(), "Elementor", page_url="https://acme.test/p")
    assert fix.template_source == "fix_templates/elementor.yaml"
    assert fix.builder == "Elementor"


# ─── client messages ─────────────────────────────────────────────────────────
def test_client_message_escapes_a_malicious_anchor_text():
    """Anchor text is scanned page content. It must not inject into an email."""
    f = _finding(anchor_text='<img src=x onerror=alert(1)>')
    message = render_client_message(f, page_url="https://acme.test/p",
                                    site_url="https://acme.test")
    assert "<img" not in message["body"]
    assert "&lt;img" in message["body"]


def test_client_message_escapes_a_malicious_url():
    f = _finding(url='https://acme.test/"><script>alert(1)</script>')
    message = render_client_message(f, page_url="https://acme.test/p",
                                    site_url="https://acme.test")
    assert "<script>" not in message["body"]


@pytest.mark.parametrize("issue_type,finding", [
    (BROKEN_LINK, _finding()),
    (EXTERNAL_DOWN, _finding(is_external=True)),
    (MISSING_ASSET, _finding(resource_type="script")),
    (DEAD_CTA, _finding(bucket="dead_cta")),
    (REDIRECT_CHAIN, _finding(bucket="ok", redirect_flags=["long_chain"],
                              redirect_chain=[{"url": "https://a.test/1", "status": 301},
                                              {"url": "https://a.test/2", "status": 200}])),
    (MIXED_CONTENT, _finding(url="http://acme.test/a.js", resource_type="script")),
])
def test_every_issue_category_has_a_client_message(issue_type, finding):
    message = render_client_message(finding, page_url="https://acme.test/p",
                                    site_url="https://acme.test")
    assert message["issue_type"] == issue_type
    assert message["subject"] and message["body"]
    assert "{" not in message["body"] and "}" not in message["body"]


def test_report_summary_renders():
    summary = render_report_summary(site_url="https://acme.test",
                                    summary_line="1 new · 0 fixed · 2 still open",
                                    new_count=1)
    assert "1 new" in summary["body"]
    assert "{" not in summary["body"]


# ─── choosing a builder when detection is ambiguous ──────────────────────────
# Regression: apexure.com detected as ["Unbounce", "Framer"] — a contradiction,
# since at least one must be wrong. The Fix Pack picked builders[0] and rendered
# Unbounce steps. Guessing here sends a client into the wrong editor.
def test_contradictory_builders_fall_back_to_generic():
    assert choose_builder(["Unbounce", "Framer"]) == ""
    assert choose_builder(["Shopify", "Elementor"]) == ""


def test_a_single_builder_is_used():
    assert choose_builder(["Elementor"]) == "Elementor"


def test_builders_that_share_a_template_are_not_a_contradiction():
    """Divi and Gutenberg both mean WordPress; one template serves both."""
    assert template_slug(choose_builder(["Divi", "Gutenberg"])) == "wordpress"


def test_unknown_builders_are_ignored():
    assert choose_builder(["Hugo", "Jekyll"]) == ""
    assert choose_builder([]) == ""


def test_a_contradictory_detection_renders_generic_steps():
    fix = build_fix_suggestion(_finding(), choose_builder(["Unbounce", "Framer"]),
                               page_url="https://acme.test/p")
    assert fix.template_source == "fix_templates/generic.yaml"


# ─── the suggestion sentence ────────────────────────────────────────────────
# Templates used to write "Suggested replacement: {proposed_value}. Confirm it
# is right." which rendered as "Suggested replacement: none. Confirm it is
# right." when nothing could be suggested — nonsense in front of a client.
def test_a_suggestion_is_offered_with_a_warning_to_confirm_it():
    f = _finding(redirect_chain=[{"url": "https://acme.test/gone", "status": 301},
                                 {"url": "https://acme.test/new", "status": 404}])
    steps = " ".join(build_fix_suggestion(f, "Elementor", page_url="https://acme.test/p").steps)
    assert "Suggested replacement: https://acme.test/new" in steps
    assert "Confirm this is correct" in steps


def test_no_suggestion_says_so_plainly_and_never_says_confirm_it():
    steps = " ".join(build_fix_suggestion(_finding(), "Elementor",
                                          page_url="https://acme.test/p").steps)
    assert "cannot suggest a replacement" in steps
    assert "Suggested replacement: none" not in steps
    assert "Confirm this is correct" not in steps


@pytest.mark.parametrize("builder", ["", "Elementor", "GoHighLevel", "ClickFunnels",
                                     "Unbounce", "Gutenberg", "Shopify", "Astro"])
def test_no_template_phrases_the_suggestion_itself(builder):
    """Each template defers to {suggestion_sentence}; none hard-codes the phrasing."""
    steps = " ".join(build_fix_suggestion(_finding(), builder,
                                          page_url="https://acme.test/p").steps)
    assert "Suggested replacement: none" not in steps
