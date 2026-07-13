"""The Intent Map — promise classification + fulfillment, deterministic."""
from promise_classifier import classify, severity_for_zone
from fulfillment_verifier import verify


# ── classifier: positives ──
def test_cta_book_is_a_tier1_promise():
    p = classify("Book your free consultation", zone="cta")
    assert p and p["type"] == "BOOK" and p["tier"] == 1
    assert p["confidence"] == "high" and p["weight"] == 100


def test_nav_pricing_is_purchase():
    p = classify("Pricing", zone="nav")
    assert p["type"] == "PURCHASE" and p["zone_class"] == "nav"


def test_tier2_watch_and_call_and_apply():
    assert classify("Watch the video", zone="cta")["type"] == "WATCH"
    assert classify("Call us now", zone="header")["type"] == "CALL"
    assert classify("Apply now", zone="cta")["type"] == "APPLY"
    # Tier 2 weighs below Tier 1 in the same zone
    assert classify("Watch the video", zone="cta")["weight"] < classify("Book now", zone="cta")["weight"]


def test_french_spanish_equivalents():
    assert classify("Réserver", zone="cta")["type"] == "BOOK"
    assert classify("Télécharger le guide", zone="cta")["type"] == "DOWNLOAD"
    assert classify("Contacto", zone="nav")["type"] == "CONTACT"


# ── classifier: negatives (the important ones) ──
def test_keyword_in_body_prose_is_not_a_promise():
    # "book" buried in a prose sentence link in body copy → NOT a promise
    assert classify("you can book a room at our partner hotel nearby", zone="body") is None


def test_short_body_cta_still_counts():
    # a tight, keyword-leading body anchor is a real promise
    assert classify("Book now", zone="body")["type"] == "BOOK"


def test_unknown_anchor_makes_no_promise():
    assert classify("Learn more", zone="cta") is None
    assert classify("Why us", zone="nav") is None
    assert classify("", zone="cta") is None


def test_recall_does_not_match_call():
    assert classify("Product recall notice", zone="body") is None


# ── fulfillment: each rule × honored / broken / unverified ──
def _p(t, zc="cta"):
    return {"type": t, "tier": 1, "zone_class": zc}


def test_book_honored_by_scheduling_or_form_else_broken():
    assert verify(_p("BOOK"), {"link_bucket": "ok", "integrations": ["Scheduling"]})["verdict"] == "honored"
    assert verify(_p("BOOK"), {"link_bucket": "ok", "has_form": True})["verdict"] == "honored"
    r = verify(_p("BOOK"), {"link_bucket": "ok", "integrations": [], "has_form": False})
    assert r["verdict"] == "broken" and "no way to book" in r["evidence"]


def test_download_needs_a_file():
    assert verify(_p("DOWNLOAD"), {"link_bucket": "ok", "is_file": True})["verdict"] == "honored"
    assert verify(_p("DOWNLOAD"), {"link_bucket": "ok", "is_file": False})["verdict"] == "broken"


def test_free_trial_with_payment_fields_is_broken_high():
    r = verify(_p("SIGNUP"), {"link_bucket": "ok", "has_form": True,
                              "anchor_says_free": True, "has_payment_fields": True})
    assert r["verdict"] == "broken" and r["severity"] == "high"
    # plain signup with a form is honored
    assert verify(_p("SIGNUP"), {"link_bucket": "ok", "has_form": True})["verdict"] == "honored"


def test_chat_widget_down_is_broken():
    assert verify(_p("CHAT"), {"link_bucket": "ok", "integrations": ["Chat/Support"], "chat_healthy": True})["verdict"] == "honored"
    r = verify(_p("CHAT"), {"link_bucket": "ok", "integrations": ["Chat/Support"], "chat_healthy": False})
    assert r["verdict"] == "broken" and "isn't loading" in r["evidence"]


def test_call_needs_tel_or_phone():
    assert verify(_p("CALL"), {"link_bucket": "ok", "is_tel": True})["verdict"] == "honored"
    assert verify(_p("CALL"), {"link_bucket": "ok", "is_tel": False, "has_phone": False})["verdict"] == "broken"


def test_bot_blocked_destination_is_unverified_never_broken():
    for t in ("BOOK", "DOWNLOAD", "CONTACT", "PURCHASE", "SIGNUP", "WATCH", "CHAT"):
        r = verify(_p(t), {"link_bucket": "unverifiable"})
        assert r["verdict"] == "unverified"


def test_broken_destination_is_broken_promise():
    assert verify(_p("CONTACT"), {"link_bucket": "broken"})["verdict"] == "broken"


def test_purchase_redirect_to_home_is_broken_else_unverified():
    assert verify(_p("PURCHASE"), {"link_bucket": "ok", "redirect_to_home": True})["verdict"] == "broken"
    # can't see pricing content from link data → unverified, not a false "broken"
    assert verify(_p("PURCHASE"), {"link_bucket": "ok"})["verdict"] == "unverified"


# ── zone severity ──
def test_zone_severity_ladder():
    assert severity_for_zone("cta") == "critical"
    assert severity_for_zone("nav") == "high"
    assert severity_for_zone("body") == "medium"


# ── orchestration ──
from intent_map import compute_intent_map


def _link(anchor, zone, url, bucket="ok", **kw):
    return {"anchor_text": anchor, "zones": [zone], "url": url, "bucket": bucket, "label": bucket, **kw}


def test_map_verdict_all_honored():
    links = [_link("Book a demo", "cta", "https://x.com/book"),
             _link("Pricing", "nav", "https://x.com/pricing", redirect_chain=[])]
    m = compute_intent_map(links, integration_categories={"Scheduling"}, has_site_form=True)
    # BOOK honored (scheduling); PURCHASE unverified (no pricing signal) — 0 broken
    assert m["counts"]["broken"] == 0
    assert "honored" in m["verdict"]


def test_map_broken_promise_promoted_and_counted():
    links = [_link("Book your consultation", "cta", "https://x.com/book")]  # no scheduler, no form
    m = compute_intent_map(links, integration_categories=set(), has_site_form=False)
    assert m["counts"]["broken"] == 1 and m["all_clear"] is False
    assert m["promises"][0]["verdict"] == "broken"          # broken promoted to top
    assert m["promises"][0]["severity"] == "critical"       # CTA zone
    assert "broken" in m["verdict"]


def test_map_ignores_non_promise_links():
    links = [_link("Learn more", "cta", "https://x.com/a"), _link("Home", "nav", "https://x.com/")]
    assert compute_intent_map(links)["counts"]["conversion_total"] == 0


def test_download_file_is_honored_via_link_itself():
    links = [_link("Download the guide", "cta", "https://x.com/guide.pdf")]
    m = compute_intent_map(links)
    assert m["promises"][0]["verdict"] == "honored" and m["promises"][0]["type"] == "DOWNLOAD"
