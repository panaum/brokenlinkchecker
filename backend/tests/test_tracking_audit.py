"""
Tracking & pixel integrity audit.

Two things are pinned:

1. The right flags fire — duplicate ids, a form with no tracking, UTMs dropped
   across a redirect, a thank-you page with no event.
2. A tracking finding is NEVER `broken`. A mis-fired pixel is a marketing
   problem, not a dead link; it must never turn a report red, dent the health
   score, or wake anyone on the monitoring schedule.
"""
import re

import pytest
from bs4 import BeautifulSoup

import tracking_audit as T
from tracking_audit import (
    audit_tracking,
    dropped_attribution,
    extract_tracking,
)

PAGE = "https://acme.test/pricing"


def _soup(html):
    return BeautifulSoup(html, "lxml")


def _sig(html, forms=None):
    return {"tracking": extract_tracking(_soup(html)), "forms": forms or []}


# ─── extraction ──────────────────────────────────────────────────────────────
GTM = '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-ABCDE"></script>'
GA4 = ("<script>gtag('config', 'G-1234567890');</script>")
META = ("<script>fbq('init', '1234567890'); fbq('track', 'PageView');</script>")


def test_it_reads_a_gtm_container_id():
    t = extract_tracking(_soup(GTM))
    assert "GTM-ABCDE" in t["gtm"]


def test_it_reads_a_ga4_measurement_id():
    t = extract_tracking(_soup(GA4))
    assert "G-1234567890" in t["ga4"]
    assert t["has_gtag"] is True


def test_it_reads_a_meta_pixel_id_and_sees_the_event():
    t = extract_tracking(_soup(META))
    assert "1234567890" in t["meta_pixel"]
    assert t["has_event"] is True


def test_a_page_with_nothing_reports_no_tracking():
    t = extract_tracking(_soup("<html><body><h1>hi</h1></body></html>"))
    assert t["any_tracking"] is False
    assert t["has_event"] is False


# ─── duplicate ids ───────────────────────────────────────────────────────────
def test_a_pixel_loaded_twice_is_flagged_as_double_counting():
    html = META + META
    findings = audit_tracking(_sig(html), [], PAGE)
    dupes = [f for f in findings if "double-counted" in f.reason]
    assert len(dupes) == 1
    assert dupes[0].bucket == "unverifiable"


def test_a_pixel_loaded_once_is_not_a_duplicate():
    findings = audit_tracking(_sig(META), [], PAGE)
    assert not any("double-counted" in f.reason for f in findings)


def test_gtm_and_ga4_with_the_same_suffix_do_not_collide():
    # "GTM-ABC" and "G-ABC..." are different vendors — not a duplicate.
    html = '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-ABCDEF"></script>' \
           "<script>gtag('config','G-ABCDEF');</script>"
    assert not any("double-counted" in f.reason for f in audit_tracking(_sig(html), [], PAGE))


# ─── a form with no tracking ─────────────────────────────────────────────────
_FORM = [{"fields": [{"type": "email", "name": "email"}]}]


def test_a_form_with_no_tracking_is_flagged():
    findings = audit_tracking({"tracking": extract_tracking(_soup("<h1>no tags</h1>")),
                               "forms": _FORM}, [], PAGE)
    invisible = [f for f in findings if "conversion" in f.reason.lower()]
    assert len(invisible) == 1
    assert invisible[0].priority == "high"
    assert invisible[0].bucket == "unverifiable"


def test_a_form_with_tracking_is_not_flagged():
    findings = audit_tracking({"tracking": extract_tracking(_soup(GA4)),
                               "forms": _FORM}, [], PAGE)
    assert not any("no analytics" in f.reason for f in findings)


def test_no_form_means_no_form_without_tracking_flag():
    findings = audit_tracking(_sig("<h1>plain page</h1>"), [], PAGE)
    assert not any("has a form" in f.reason for f in findings)


# ─── UTM survival across a redirect ──────────────────────────────────────────
def _chain(*urls):
    return [{"url": u, "status": 301 if i < len(urls) - 1 else 200}
            for i, u in enumerate(urls)]


def test_utms_dropped_across_a_redirect_are_flagged():
    dropped = dropped_attribution(_chain(
        "https://acme.test/go?utm_source=google&utm_campaign=spring",
        "https://acme.test/landing"))
    assert dropped == {"utm_source", "utm_campaign"}


def test_utms_preserved_across_a_redirect_are_not_flagged():
    dropped = dropped_attribution(_chain(
        "https://acme.test/go?utm_source=google",
        "https://acme.test/landing?utm_source=google"))
    assert dropped == set()


def test_a_click_id_dropped_on_redirect_is_flagged():
    dropped = dropped_attribution(_chain(
        "https://acme.test/go?gclid=abc123", "https://acme.test/final"))
    assert dropped == {"gclid"}


def test_no_redirect_means_no_utm_finding():
    assert dropped_attribution([]) == set()
    assert dropped_attribution([{"url": "https://acme.test/x?utm_source=g", "status": 200}]) == set()


class _Res:
    def __init__(self, url, chain):
        self.url = url
        self.redirect_chain = chain


def test_a_dropped_utm_flows_into_a_finding():
    res = [_Res("https://acme.test/go?utm_source=google",
                _chain("https://acme.test/go?utm_source=google", "https://acme.test/end"))]
    findings = audit_tracking(_sig(GA4), res, PAGE)
    utm = [f for f in findings if "attribution" in f.reason.lower()]
    assert len(utm) == 1
    assert utm[0].priority == "high" and utm[0].bucket == "unverifiable"


# ─── thank-you / conversion page ─────────────────────────────────────────────
def test_a_thankyou_page_with_no_event_is_high_priority():
    findings = audit_tracking(_sig("<h1>Thanks!</h1>"), [], "https://acme.test/thank-you")
    conv = [f for f in findings if "thank-you" in f.reason.lower() or "confirmation" in f.reason.lower()]
    assert len(conv) == 1
    assert conv[0].priority == "high"
    assert conv[0].bucket == "unverifiable"


def test_a_thankyou_page_with_an_event_is_not_flagged():
    findings = audit_tracking(_sig(META), [], "https://acme.test/order/success")
    assert not any("not recording" in f.reason for f in findings)


def test_an_ordinary_page_with_no_event_is_not_a_conversion_flag():
    findings = audit_tracking(_sig("<h1>About us</h1>"), [], "https://acme.test/about")
    assert not any("thank" in f.reason.lower() for f in findings)


# ─── expected-id mismatch ────────────────────────────────────────────────────
def test_a_page_with_the_wrong_ga4_id_is_flagged():
    findings = audit_tracking(_sig("<script>gtag('config','G-WRONG99')</script>"),
                              [], PAGE, expected={"ga4": "G-RIGHT11"})
    mism = [f for f in findings if "wrong account" in f.reason.lower()]
    assert len(mism) == 1 and mism[0].priority == "high"


def test_a_page_with_the_right_ga4_id_is_not_flagged():
    findings = audit_tracking(_sig("<script>gtag('config','G-RIGHT11')</script>"),
                              [], PAGE, expected={"ga4": "G-RIGHT11"})
    assert not any("wrong account" in f.reason.lower() for f in findings)


def test_no_expected_ids_means_no_mismatch_check():
    findings = audit_tracking(_sig("<script>gtag('config','G-ANYTHING')</script>"),
                              [], PAGE, expected=None)
    assert not any("wrong account" in f.reason.lower() for f in findings)


# ─── the hard rule: never broken ─────────────────────────────────────────────
def test_no_tracking_finding_is_ever_broken():
    """Every path, every fixture — a tracking finding is at most unverifiable."""
    scenarios = [
        (_sig(META + META), []),                                  # duplicate
        ({"tracking": extract_tracking(_soup("<h1>x</h1>")), "forms": _FORM}, []),  # form-no-tracking
        (_sig(GA4), [_Res("u", _chain("https://x/a?utm_source=g", "https://x/b"))]),  # utm drop
        (_sig("<h1>thanks</h1>"), []),                            # thank-you (via url below)
    ]
    for sig, res in scenarios:
        for f in audit_tracking(sig, res, "https://acme.test/thank-you", expected={"ga4": "G-RIGHT"}):
            assert f.bucket != "broken", f.reason
            assert f.bucket == "unverifiable"
            assert f.category == "Tracking"
            assert f.label == "tracking"


def test_the_module_makes_no_network_request_and_uses_no_llm():
    import pathlib
    src = pathlib.Path(__file__).parent.parent.joinpath("tracking_audit.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for banned in ("httpx", "aiohttp", "requests.get", "requests.post",
                   "urlopen", "socket.", "openai", "anthropic"):
        assert banned not in code, banned


# ─── false positives caught on the real apexure.com scan ─────────────────────
# A correctly-installed GTM mentions its id TWICE in the HTML: the inline
# bootstrap and the <noscript> fallback iframe. Counting mentions would flag
# every proper GTM install as double-counted.
_GTM_SINGLE_INSTALL = """
<head>
<script>(function(w,d,s,l,i){w[l]=w[l]||[];})(window,document,'script','dataLayer','GTM-P593C44');</script>
</head>
<body>
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-P593C44"></iframe></noscript>
</body>
"""


def test_one_correct_gtm_install_is_not_a_duplicate():
    findings = audit_tracking(_sig(_GTM_SINGLE_INSTALL), [], PAGE)
    assert not any("double-counted" in f.reason for f in findings), \
        "inline + noscript is one install, not a duplicate"


def test_two_real_gtm_bootstraps_are_a_duplicate():
    html = _GTM_SINGLE_INSTALL + \
        "<script>(function(w,d,s,l,i){})(window,document,'script','dataLayer','GTM-P593C44');</script>"
    findings = audit_tracking(_sig(html), [], PAGE)
    assert any("double-counted" in f.reason for f in findings)


def test_a_placeholder_gtm_id_is_ignored():
    """GTM-XXXXXXXXXX is an un-filled template, not a real container."""
    t = extract_tracking(_soup("<script>['GTM-XXXXXXXXXX']</script>"))
    assert t["gtm"] == []


def test_a_placeholder_ga4_id_is_ignored():
    t = extract_tracking(_soup("<script>gtag('config','G-XXXXXXX')</script>"))
    assert t["ga4"] == []


def test_a_noscript_iframe_alone_does_not_count_as_a_load():
    html = '<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-ABCDE"></iframe></noscript>'
    t = extract_tracking(_soup(html))
    # It is a fallback, not an active load — no load count, so never a duplicate.
    assert all(n <= 1 for _, _, n in t["load_counts"])
