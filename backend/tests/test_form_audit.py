"""
Passive form audit.

Two things are being pinned here.

1. Correctness of the verdicts, with a stricter bar than links: when we cannot
   PROVE a form is broken, it must be `unverifiable`. Telling a lead-gen client
   their contact form is dead when it works costs more trust than silence.

2. That the audit NEVER submits. No POST, no .submit(), no .requestSubmit(),
   no synthetic event. Submitting would spam the client's CRM and their sales
   team's phones — worse than the bug we are hunting.
"""
import asyncio
import pathlib
import re

import httpx
import pytest
from bs4 import BeautifulSoup

import form_audit
import scraper
from checker import check_all_links
from form_audit import (
    audit_forms,
    classify_form,
    extract_forms,
    form_action_links,
)


PAGE = "https://acme.test/contact"


def _soup(html):
    return BeautifulSoup(html, "lxml")


def _forms(html, **overrides):
    forms = extract_forms(_soup(html), PAGE)
    for form in forms:
        form.update(overrides)
    return forms


def _verdict(html, results=(), signals=None, **overrides):
    forms = _forms(html, **overrides)
    assert forms, "fixture has no <form>"
    by_url = {r["url"]: r for r in results}
    return classify_form(forms[0], by_url, signals or {}, PAGE)


# ─── fixtures ────────────────────────────────────────────────────────────────
HEALTHY = """
<form action="/subscribe" method="post" aria-label="Newsletter">
  <input type="email" name="email" required>
  <button type="submit">Sign up</button>
</form>
"""

NO_ACTION = """
<form aria-label="Contact form">
  <input type="text" name="name" required>
  <button type="submit">Send</button>
</form>
"""

BROKEN_ACTION = """
<form action="/handlers/gone" method="post" aria-label="Contact form">
  <input type="email" name="email" required>
  <button type="submit">Send</button>
</form>
"""

NO_SUBMIT = """
<form action="/subscribe" method="post" aria-label="Newsletter">
  <input type="email" name="email" required>
</form>
"""

REQUIRED_WITHOUT_NAME = """
<form action="/subscribe" method="post" aria-label="Contact form">
  <input type="email" id="email-field" required>
  <button type="submit">Send</button>
</form>
"""

HIDDEN = """
<form action="/subscribe" method="post" aria-label="Popup form" style="display:none">
  <input type="email" name="email" required>
  <button type="submit">Send</button>
</form>
"""

SEARCH = """
<form action="/search" method="get" role="search" id="search-form">
  <input type="search" name="q">
</form>
"""

HUBSPOT_EMBED = """
<script src="https://js.hs-scripts.com/12345.js"></script>
<div class="hs-form"></div>
<form action="/hs" aria-label="Request a demo">
  <input type="email" name="email" required>
  <button type="submit">Send</button>
</form>
"""


def _ok(url):
    return {"url": url, "bucket": "ok", "status_code": 200}


def _broken(url, status=404):
    return {"url": url, "bucket": "broken", "status_code": status}


def _unverifiable(url, status=403):
    return {"url": url, "bucket": "unverifiable", "status_code": status}


def _server_error(url):
    return {"url": url, "bucket": "broken", "status_code": 500}


def _dead_host(url):
    return {"url": url, "bucket": "broken", "status_code": None}


# ─── the six required fixtures ───────────────────────────────────────────────
def test_healthy_form_produces_no_finding():
    assert _verdict(HEALTHY, results=[_ok("https://acme.test/subscribe")],
                    visible=True) is None


def test_form_with_no_action_and_no_handler_is_a_dead_cta():
    verdict = _verdict(NO_ACTION, visible=True)
    assert verdict["bucket"] == "dead_cta"
    assert "submits nowhere" in verdict["reason"]


def test_form_posting_to_a_404_is_a_dead_cta():
    verdict = _verdict(BROKEN_ACTION,
                       results=[_broken("https://acme.test/handlers/gone")],
                       visible=True)
    assert verdict["bucket"] == "dead_cta"
    assert "returns 404" in verdict["reason"]
    assert "submissions may be lost" in verdict["reason"]


def test_form_without_a_submit_control_is_a_dead_cta():
    verdict = _verdict(NO_SUBMIT, results=[_ok("https://acme.test/subscribe")],
                       visible=True)
    assert verdict["bucket"] == "dead_cta"
    assert "no button to submit" in verdict["reason"]


def test_required_field_without_a_name_is_broken():
    """The visitor types into it and the value never reaches the server."""
    verdict = _verdict(REQUIRED_WITHOUT_NAME,
                       results=[_ok("https://acme.test/subscribe")], visible=True)
    assert verdict["bucket"] == "broken"
    assert "never" in verdict["reason"] and "discarded" in verdict["reason"]


def test_a_css_hidden_form_is_not_reported_at_all():
    """display:none is the resting state of every modal contact form on the
    internet. Reporting it would tell most clients their working popup "may be
    unreachable" — noise on nearly every site, and never a defect."""
    assert _verdict(HIDDEN, results=[_ok("https://acme.test/subscribe")]) is None


def test_a_form_rendered_at_zero_size_is_unverifiable():
    """Displayed but 0x0 is a rendering failure, not a design choice."""
    verdict = _verdict(HEALTHY, results=[_ok("https://acme.test/subscribe")],
                       visible=False, hidden_reason="zero-size")
    assert verdict["bucket"] == "unverifiable"
    assert "no size" in verdict["reason"]


def test_a_css_hidden_form_with_a_dead_endpoint_is_still_a_dead_cta():
    verdict = _verdict(HIDDEN, results=[_broken("https://acme.test/subscribe", 404)])
    assert verdict["bucket"] == "dead_cta"


def test_form_covered_by_an_overlay_is_unverifiable():
    verdict = _verdict(HEALTHY, results=[_ok("https://acme.test/subscribe")],
                       visible=True, covered=True)
    assert verdict["bucket"] == "unverifiable"
    assert "covered by something else" in verdict["reason"]


# ─── the "cannot prove it" rule ──────────────────────────────────────────────
# ─── what a GET to a form action actually proves ────────────────────────────
# Verified against real endpoints: EmailOctopus, HubSpot and Formspree all
# return 405 to a GET. They accept POST and nothing else. A 405 is the sign of
# a HEALTHY form endpoint. Reporting it would flag almost every form in
# existence, and the first real scan (apexure.com) did exactly that.
@pytest.mark.parametrize("status", [400, 401, 403, 405, 429])
def test_an_endpoint_that_refuses_a_get_is_not_a_finding(status):
    verdict = _verdict(BROKEN_ACTION,
                       results=[_unverifiable("https://acme.test/handlers/gone", status)],
                       visible=True)
    assert verdict is None


def test_a_500_on_a_post_only_endpoint_is_never_called_broken():
    """The checker buckets 5xx as `broken`. A POST endpoint may 500 on a GET, so
    for a FORM that is a soft warning, not a lost-submissions claim."""
    verdict = _verdict(BROKEN_ACTION,
                       results=[_server_error("https://acme.test/handlers/gone")],
                       visible=True)
    assert verdict["bucket"] == "unverifiable"
    assert "submissions may be lost" not in verdict["reason"]


@pytest.mark.parametrize("status", [404, 410])
def test_only_a_gone_status_proves_the_form_posts_nowhere(status):
    verdict = _verdict(BROKEN_ACTION,
                       results=[_broken("https://acme.test/handlers/gone", status)],
                       visible=True)
    assert verdict["bucket"] == "dead_cta"


def test_a_dead_host_proves_the_form_posts_nowhere():
    verdict = _verdict(BROKEN_ACTION,
                       results=[_dead_host("https://acme.test/handlers/gone")],
                       visible=True)
    assert verdict["bucket"] == "dead_cta"
    assert "no longer exists" in verdict["reason"]


def test_action_verdict_table():
    from form_audit import ACTION_FINE, ACTION_GONE, ACTION_UNCERTAIN, action_verdict
    assert action_verdict({"status_code": 404, "bucket": "broken"}) == ACTION_GONE
    assert action_verdict({"status_code": 405, "bucket": "unverifiable"}) == ACTION_FINE
    assert action_verdict({"status_code": 200, "bucket": "ok"}) == ACTION_FINE
    assert action_verdict({"status_code": 500, "bucket": "broken"}) == ACTION_UNCERTAIN
    assert action_verdict(None) == ACTION_UNCERTAIN


def test_an_unchecked_action_yields_no_finding():
    """No result for the action means we never checked it. Say nothing."""
    assert _verdict(BROKEN_ACTION, results=[], visible=True) is None


def test_a_js_handler_means_no_action_is_fine():
    verdict = _verdict(NO_ACTION, visible=True, has_js_submit_listener=True)
    assert verdict is None


def test_an_inline_onsubmit_means_no_action_is_fine():
    verdict = _verdict(NO_ACTION, visible=True, has_inline_onsubmit=True)
    assert verdict is None


def test_a_delegated_page_never_calls_an_action_less_form_dead():
    """React attaches one listener on document. Absence on the form proves nothing."""
    verdict = _verdict(NO_ACTION, signals={"delegated": True}, visible=True)
    assert verdict is None


def test_a_broken_endpoint_beats_hidden():
    """Visibility is uncertain; a 404 endpoint is not. The endpoint wins."""
    verdict = _verdict(HIDDEN, results=[_broken("https://acme.test/subscribe", 404)])
    assert verdict["bucket"] == "dead_cta"


# ─── search forms ────────────────────────────────────────────────────────────
def test_a_search_form_without_a_button_is_not_flagged():
    """You submit a search box with Enter. Flagging these is noise on every site."""
    assert _verdict(SEARCH, results=[_ok("https://acme.test/search")],
                    visible=True) is None


# ─── embed scripts ───────────────────────────────────────────────────────────
def test_a_failed_embed_script_means_the_form_never_renders():
    signals = {"http_errors": [
        {"url": "https://js.hs-scripts.com/12345.js", "status": 404,
         "resource_type": "script"},
    ]}
    verdict = _verdict(HUBSPOT_EMBED, results=[_ok("https://acme.test/hs")],
                       signals=signals, visible=True)
    assert verdict["bucket"] == "dead_cta"
    assert "never appears" in verdict["reason"]
    assert "12345.js" in verdict["reason"]


def test_a_healthy_embed_script_is_not_flagged():
    assert _verdict(HUBSPOT_EMBED, results=[_ok("https://acme.test/hs")],
                    signals={"http_errors": []}, visible=True) is None


def test_a_failed_request_for_the_embed_also_counts():
    signals = {"failed_requests": [{"url": "https://js.hs-scripts.com/12345.js",
                                    "resource_type": "script"}]}
    verdict = _verdict(HUBSPOT_EMBED, results=[_ok("https://acme.test/hs")],
                       signals=signals, visible=True)
    assert verdict["bucket"] == "dead_cta"


# ─── extraction ──────────────────────────────────────────────────────────────
def test_action_absence_is_distinguished_from_action_to_self():
    """form.action in the DOM returns the page URL when the attribute is absent.
    Reading it would make every action-less form look like it posts to itself."""
    assert _forms(NO_ACTION)[0]["action_raw"] is None
    assert _forms(NO_ACTION)[0]["action_url"] == ""
    assert _forms(HEALTHY)[0]["action_url"] == "https://acme.test/subscribe"


def test_a_bare_button_counts_as_a_submit_control():
    html = '<form action="/x"><input name="a" required><button>Go</button></form>'
    assert _forms(html)[0]["has_submit"] is True


@pytest.mark.parametrize("control", [
    '<button type="submit">Go</button>',
    '<input type="submit" value="Go">',
    '<input type="image" src="/go.png">',
])
def test_submit_control_variants(control):
    html = f'<form action="/x"><input name="a" required>{control}</form>'
    assert _forms(html)[0]["has_submit"] is True


def test_a_reset_button_is_not_a_submit_control():
    html = '<form action="/x"><input name="a" required><button type="reset">Clear</button></form>'
    assert _forms(html)[0]["has_submit"] is False


def test_label_falls_back_through_aria_id_heading():
    assert _forms('<form aria-label="Enquiry"></form>')[0]["label"] == "Enquiry"
    assert _forms('<form id="signup"></form>')[0]["label"] == "signup"
    assert _forms('<form><h3>Book a call</h3></form>')[0]["label"] == "Book a call"
    assert _forms("<form></form>")[0]["label"] == "Form #1"


def test_statically_hidden_forms_are_marked_not_visible():
    assert _forms(HIDDEN)[0]["visible"] is False
    assert _forms('<form hidden action="/x"></form>')[0]["visible"] is False
    assert _forms(HEALTHY)[0]["visible"] is None   # unknown without a browser


# ─── reuse of the existing checker ───────────────────────────────────────────
def test_form_actions_become_rawlinks_for_the_existing_checker():
    links = form_action_links(_forms(HEALTHY), PAGE)
    assert len(links) == 1
    assert links[0].url == "https://acme.test/subscribe"
    assert links[0].resource_type == "form_action"
    assert links[0].category == "Form"
    assert links[0].priority == "critical"


def test_action_less_forms_produce_no_link_to_check():
    assert form_action_links(_forms(NO_ACTION), PAGE) == []


def test_a_mailto_action_is_not_fetched():
    links = form_action_links(_forms('<form action="mailto:a@b.test"></form>'), PAGE)
    assert links == []


def test_an_already_seen_action_is_not_duplicated():
    assert form_action_links(_forms(HEALTHY), PAGE,
                             already_seen={"https://acme.test/subscribe"}) == []


# ─── findings enter the normal pipeline ──────────────────────────────────────
def test_audit_forms_yields_linkresults_that_diff_like_any_finding():
    findings = audit_forms(_forms(NO_ACTION, visible=True), [], {}, PAGE)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.bucket == "dead_cta"
    assert finding.category == "Form"
    assert finding.link_kind == "form"
    assert finding.priority == "critical"
    assert finding.url.startswith(PAGE)      # stable identity for the diff


def test_healthy_forms_produce_no_findings():
    results = [_ok("https://acme.test/subscribe")]
    assert audit_forms(_forms(HEALTHY, visible=True), results, {}, PAGE) == []


def test_finding_identity_is_stable_across_scans():
    a = audit_forms(_forms(NO_ACTION, visible=True), [], {}, PAGE)[0]
    b = audit_forms(_forms(NO_ACTION, visible=True), [], {}, PAGE)[0]
    assert a.url == b.url and a.anchor_text == b.anchor_text


def test_reason_is_business_language_not_jargon():
    verdict = _verdict(BROKEN_ACTION,
                       results=[_broken("https://acme.test/handlers/gone")],
                       visible=True)
    reason = verdict["reason"].lower()
    assert "submissions may be lost" in reason
    for jargon in ("action unreachable", "http", "endpoint 404", "dom"):
        assert jargon not in reason


# ─────────────────────────────────────────────────────────────────────────────
# THE HARD CONSTRAINT: this feature never submits a form.
# ─────────────────────────────────────────────────────────────────────────────
_SUBMIT_PATTERNS = re.compile(
    r"\.submit\s*\(|requestSubmit|\.click\s*\(|dispatchEvent|"
    r"new\s+SubmitEvent|method\s*=\s*[\"']post[\"']|client\.post|\.post\s*\(",
    re.IGNORECASE,
)


@pytest.mark.parametrize("path", ["form_audit.py", "scraper.py"])
def test_no_source_file_can_submit_a_form(path):
    source = (pathlib.Path(__file__).parent.parent / path).read_text(encoding="utf-8")
    # Strip comments and docstrings: they discuss submission, they do not do it.
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    for block in re.findall(r'"""(.*?)"""', code, re.DOTALL):
        code = code.replace(block, "")
    offenders = _SUBMIT_PATTERNS.findall(code)
    assert not offenders, f"{path} contains submission-shaped code: {offenders}"


def test_the_collect_forms_script_only_reads():
    js = scraper._COLLECT_FORMS_JS
    for forbidden in (".submit(", "requestSubmit", ".click(", "dispatchEvent",
                      "new SubmitEvent", "fetch(", "XMLHttpRequest"):
        assert forbidden not in js, forbidden


def test_the_audit_issues_no_http_request_at_all():
    """classify_form and audit_forms are pure: they read results, never fetch."""
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport):
            audit_forms(_forms(BROKEN_ACTION, visible=True),
                        [_broken("https://acme.test/handlers/gone")], {}, PAGE)

    asyncio.run(run())
    assert calls == []


def test_checking_a_form_action_uses_get_never_post():
    """Form actions go through the ordinary checker, which only ever GETs."""
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(200)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as c:
            import checker
            for link in form_action_links(_forms(HEALTHY), PAGE):
                await checker.check_single(c, link)

    asyncio.run(run())
    assert methods == ["GET"]


def test_the_listener_probe_records_submit_but_never_fires_it():
    from dead_cta_detector import LISTENER_PROBE_JS
    assert "'submit'" in LISTENER_PROBE_JS          # observed
    assert ".submit(" not in LISTENER_PROBE_JS      # never invoked
    assert "dispatchEvent" not in LISTENER_PROBE_JS


# ─────────────────────────────────────────────────────────────────────────────
# Regression: hubspot.com carries two <input type=search name=q> forms with
# action="" and no submit button. An earlier version of this file identified
# search forms by id/label/action only, so it missed both. They escaped a
# "dead CTA" verdict purely because they happened to be hidden or covered — one
# CSS rule away from telling HubSpot their search box was broken.
# ─────────────────────────────────────────────────────────────────────────────
HUBSPOT_SEARCH = """
<form action="" method="get">
  <input type="search" name="q" placeholder="Search HubSpot">
</form>
"""


def test_a_nameless_search_form_is_never_flagged():
    assert _verdict(HUBSPOT_SEARCH, visible=True) is None
    assert _verdict(HUBSPOT_SEARCH, visible=True, covered=True) is None


@pytest.mark.parametrize("field", [
    '<input type="search" name="whatever">',
    '<input type="text" name="q">',
    '<input type="text" name="query">',
    '<input type="text" name="s">',
    '<input type="text" name="x" placeholder="Search the site">',
])
def test_search_forms_are_recognised_by_their_fields(field):
    html = f'<form action="/x">{field}</form>'
    assert _verdict(html, visible=True) is None


def test_a_role_search_form_is_exempt():
    html = '<form role="search" action="/x"><input type="text" name="anything"></form>'
    assert _verdict(html, visible=True) is None


def test_a_contact_form_is_not_mistaken_for_a_search_form():
    html = '<form aria-label="Contact"><input type="email" name="email" required></form>'
    verdict = _verdict(html, visible=True)
    assert verdict is not None and verdict["bucket"] == "dead_cta"


def test_a_form_with_no_typable_fields_is_ignored():
    """A wrapper, a logout stub, a single-button POST: nothing to collect."""
    html = '<form action="/logout" method="post"><input type="hidden" name="csrf" value="x"></form>'
    assert _verdict(html, visible=True) is None


def test_a_form_of_only_buttons_is_ignored():
    assert _verdict('<form action="/x"><button>Go</button></form>', visible=True) is None


def test_a_research_form_is_not_mistaken_for_a_search_box():
    """"/research/" contains "search". A substring match would silently exempt a
    real lead-capture form from every check below it."""
    html = ('<form action="/research/subscribe" aria-label="Download our research report">'
            '<input type="email" name="email" required></form>')
    verdict = _verdict(html, results=[], visible=True)
    assert verdict is not None      # no submit button -> a real finding
    assert verdict["bucket"] == "dead_cta"


@pytest.mark.parametrize("action", ["/research/x", "/researcher", "/searching-tips"])
def test_words_containing_search_do_not_exempt_a_form(action):
    from form_audit import _is_search_form
    form = {"identifier": "", "label": "", "action_url": action, "role": "",
            "fields": [{"tag": "input", "type": "email", "name": "email",
                        "placeholder": "", "required": True}]}
    assert _is_search_form(form) is False


@pytest.mark.parametrize("action", ["/search", "/site-search?x=1", "/search/results"])
def test_a_real_search_path_still_exempts(action):
    from form_audit import _is_search_form
    form = {"identifier": "", "label": "", "action_url": action, "role": "",
            "fields": [{"tag": "input", "type": "text", "name": "term",
                        "placeholder": "", "required": False}]}
    assert _is_search_form(form) is True


# ─── healthy forms are visible, not silent ───────────────────────────────────
# "0 findings" used to mean both "we looked and it is fine" and "we never
# looked". apexure.com's real contact form has no action attribute and submits
# via fetch, so it produced no action link and no finding: it was absent from
# the report entirely.
_JS_CONTACT_FORM = """
<form id="contact">
  <input type="text" name="name" required placeholder="Full name">
  <input type="email" name="email" required placeholder="Work email">
  <button type="submit">Send</button>
</form>
"""


def _rows(html, results=(), signals=None, **overrides):
    forms = _forms(html, **overrides)
    return audit_forms(forms, list(results), signals or {}, PAGE)


def test_a_healthy_js_form_gets_a_visible_working_row():
    rows = _rows(_JS_CONTACT_FORM, has_js_submit_listener=True)
    assert len(rows) == 1
    assert rows[0].bucket == "ok" and rows[0].label == "ok"
    assert rows[0].category == "Form"


def test_the_healthy_row_admits_it_cannot_see_where_a_js_form_posts():
    row = _rows(_JS_CONTACT_FORM, has_js_submit_listener=True)[0]
    assert "never submit" in row.reason
    assert "cannot be verified" in row.reason


def test_a_healthy_row_carries_no_priority_so_it_shows_no_chip():
    assert _rows(_JS_CONTACT_FORM, has_js_submit_listener=True)[0].priority is None


def test_a_healthy_form_is_never_a_diff_finding():
    """bucket=ok is skipped by diffing.py, so it cannot enter a snapshot."""
    from diffing import collect_findings
    rows = _rows(_JS_CONTACT_FORM, has_js_submit_listener=True)
    assert collect_findings(PAGE, rows) == []


def test_a_search_box_gets_no_row_at_all():
    html = '<form><input type="search" name="q"></form>'
    assert _rows(html, has_js_submit_listener=True) == []


def test_a_form_with_an_http_action_is_not_listed_twice():
    """Its action is already a checked row; a second row would double-count it."""
    html = ('<form action="https://forms.test/submit">'
            '<input type="email" name="e" required><button type="submit">Go</button></form>')
    assert _rows(html) == []


def test_a_broken_form_still_reports_the_defect_not_a_healthy_row():
    html = ('<form action="https://forms.test/gone">'
            '<input type="email" name="e" required><button type="submit">Go</button></form>')
    checked = [{"url": "https://forms.test/gone", "status_code": 404, "bucket": "broken",
                "resource_type": "form_action"}]
    rows = _rows(html, results=checked)
    assert [r.bucket for r in rows] == ["dead_cta"]


# ─── a 405 proves the endpoint is live ───────────────────────────────────────
class _Row:
    def __init__(self, **kw):
        self.resource_type = "form_action"
        self.bucket = "unverifiable"
        self.label = "blocked"
        self.priority = "critical"
        self.status_code = 405
        self.reason = None
        self.error = "blocked"
        self.url = "https://forms.test/submit"
        self.__dict__.update(kw)


def test_a_405_form_action_is_promoted_to_working():
    rows = [_Row()]
    assert form_audit.relabel_form_actions(rows) == 1
    assert rows[0].bucket == "ok" and rows[0].label == "ok"
    assert rows[0].priority is None and rows[0].error is None
    assert "405" in rows[0].reason


@pytest.mark.parametrize("status", [401, 403, 429, 500, 404])
def test_only_405_is_promoted(status):
    """403 is equally the fingerprint of a bot wall. It stays unverifiable."""
    rows = [_Row(status_code=status)]
    assert form_audit.relabel_form_actions(rows) == 0
    assert rows[0].bucket == "unverifiable"


def test_ordinary_links_are_never_touched():
    rows = [_Row(resource_type="anchor")]
    assert form_audit.relabel_form_actions(rows) == 0
    assert rows[0].bucket == "unverifiable"
