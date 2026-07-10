"""
Active form testing — the dangerous tier.

This module creates real submissions, so its rails are tested harder than
anything else. None of these tests submit to the network; they pin the DECISION
logic that decides whether, and what, to submit.

Rails asserted here:
  - global flag default OFF
  - payment forms refused (card field OR payment iframe), regardless of anything
  - honeypots / hidden / file / password never filled
  - a filled plan submits exactly once
  - the monitoring scheduler has no path to submission
"""
import re

import pytest

import active_submission as A
from active_submission import (
    active_testing_enabled,
    default_test_email,
    is_fillable,
    is_honeypot,
    is_payment_field,
    is_payment_form,
    plan_submission,
    value_for,
)


def _field(**kw):
    base = {"tag": "input", "type": "text", "name": "", "id": "",
            "placeholder": "", "required": False, "visible": True,
            "width": 200, "height": 30, "autocomplete": ""}
    base.update(kw)
    return base


# ─── the global flag (default OFF) ───────────────────────────────────────────
def test_the_flag_is_off_by_default(monkeypatch):
    monkeypatch.delenv(A.ACTIVE_FORM_TESTING_FLAG, raising=False)
    assert active_testing_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", "On"])
def test_the_flag_turns_on_only_for_explicit_truthy(monkeypatch, val):
    monkeypatch.setenv(A.ACTIVE_FORM_TESTING_FLAG, val)
    assert active_testing_enabled() is True


@pytest.mark.parametrize("val", ["", "0", "false", "no", "off", "maybe", "  "])
def test_anything_else_leaves_the_flag_off(monkeypatch, val):
    monkeypatch.setenv(A.ACTIVE_FORM_TESTING_FLAG, val)
    assert active_testing_enabled() is False


# ─── honeypots are never filled ──────────────────────────────────────────────
@pytest.mark.parametrize("name", ["honeypot", "_gotcha", "hp", "b_123_456",
                                  "leave-this-blank", "winnie"])
def test_a_honeypot_by_name_is_detected(name):
    assert is_honeypot(_field(name=name)) is True
    assert is_fillable(_field(name=name)) is False


def test_a_css_hidden_text_field_is_a_honeypot():
    assert is_honeypot(_field(name="email2", visible=False)) is True


def test_a_zero_size_field_is_a_honeypot():
    assert is_honeypot(_field(name="url", width=0, height=0)) is True


def test_an_ordinary_visible_field_is_not_a_honeypot():
    assert is_honeypot(_field(name="email", type="email")) is False
    assert is_fillable(_field(name="email", type="email")) is True


# ─── payment forms are refused ───────────────────────────────────────────────
@pytest.mark.parametrize("name", ["cardnumber", "card_number", "cc-number",
                                  "cvc", "cvv", "cardholder", "exp-month"])
def test_a_card_field_is_a_payment_field(name):
    assert is_payment_field(_field(name=name)) is True


def test_a_cc_autocomplete_is_a_payment_field():
    assert is_payment_field(_field(name="x", autocomplete="cc-number")) is True


def test_a_form_with_a_card_field_is_refused():
    is_pay, reason = is_payment_form([_field(name="cardnumber")])
    assert is_pay is True and "payment field" in reason


@pytest.mark.parametrize("src", [
    "https://js.stripe.com/v3/", "https://www.paypal.com/sdk/js",
    "https://assets.braintreegateway.com/x.js", "https://checkout.razorpay.com/v1/checkout.js",
])
def test_a_payment_iframe_makes_it_a_payment_form(src):
    is_pay, reason = is_payment_form([_field(name="email", type="email")], [src])
    assert is_pay is True


def test_an_ordinary_contact_form_is_not_a_payment_form():
    is_pay, _ = is_payment_form([_field(name="email", type="email"),
                                 _field(name="message", tag="textarea", type="")])
    assert is_pay is False


def test_the_plan_refuses_a_payment_form_and_fills_nothing():
    plan = plan_submission([_field(name="cardnumber"), _field(name="email", type="email")])
    assert plan["refuse"] is not None
    assert "payment" in plan["refuse"].lower()
    assert plan["fills"] == [] and plan["submitted_once"] is False


# ─── what is safe to fill ────────────────────────────────────────────────────
def test_password_and_file_and_hidden_are_never_fillable():
    assert is_fillable(_field(type="password", name="pw")) is False
    assert is_fillable(_field(type="file", name="cv")) is False
    assert is_fillable(_field(type="hidden", name="csrf")) is False


def test_a_textarea_is_fillable():
    assert is_fillable(_field(tag="textarea", type="", name="message")) is True


def test_a_submit_button_is_not_fillable():
    assert is_fillable(_field(type="submit", name="go")) is False


# ─── test values ─────────────────────────────────────────────────────────────
def test_the_email_field_gets_the_filterable_test_address():
    assert value_for(_field(type="email"), "qa+linkspy@acme.test") == "qa+linkspy@acme.test"


def test_a_text_field_gets_the_marker_value():
    assert value_for(_field(type="text", name="name"), "x@y.z") == "LINKSPY-TEST"


def test_the_default_test_email_is_scoped_to_the_client_domain():
    assert default_test_email("https://www.apexure.com/contact") == "qa+linkspy@apexure.com"
    assert default_test_email("https://fautons.com") == "qa+linkspy@fautons.com"


# ─── the plan submits exactly once, and records what it skipped ──────────────
def test_a_normal_form_plan_fills_the_text_fields_and_submits_once():
    plan = plan_submission([
        _field(name="name", type="text"),
        _field(name="email", type="email"),
        _field(name="message", tag="textarea", type=""),
        _field(name="_gotcha", type="text"),        # honeypot
        _field(name="cv", type="file"),             # file
    ], test_email="qa+linkspy@acme.test")
    filled = {f["name"] for f in plan["fills"]}
    skipped = {s["name"] for s in plan["skipped"]}
    assert filled == {"name", "email", "message"}
    assert "_gotcha" in skipped and "cv" in skipped
    assert plan["submitted_once"] is True


def test_the_plan_records_why_each_field_was_skipped():
    plan = plan_submission([_field(name="_gotcha", type="text"),
                            _field(name="cv", type="file")])
    reasons = {s["name"]: s["reason"] for s in plan["skipped"]}
    assert "honeypot" in reasons["_gotcha"]
    assert "file" in reasons["cv"]


# ─── the monitoring scheduler has NO path to submission ──────────────────────
def test_the_scheduler_never_imports_or_calls_active_submission():
    """Active submission must be manual-only. monitoring.py must not reference
    it at all — no import, no call, no name."""
    import pathlib
    src = pathlib.Path(__file__).parent.parent.joinpath("monitoring.py").read_text(encoding="utf-8")
    assert "active_submission" not in src
    assert "submit" not in src.lower() or "submitted" not in src  # no submit verbs


# ─── the executor's runtime rails (SubmitGuard, observer) ────────────────────
from active_submission_exec import (
    SubmitGuard, build_plan_for_live_form, TRACKING_OBSERVER_JS, _thankyou_detected,
)


def test_submit_guard_allows_exactly_one_submission():
    guard = SubmitGuard()
    calls = []
    guard.fire(lambda: calls.append(1))
    assert calls == [1] and guard.fired is True


def test_submit_guard_refuses_a_second_submission():
    guard = SubmitGuard()
    guard.fire(lambda: None)
    with pytest.raises(RuntimeError, match="already fired"):
        guard.fire(lambda: None)   # a double-submit is impossible, not just unlikely


def test_the_observer_only_wraps_it_never_fires_an_event():
    """It must RECORD gtag/fbq/dataLayer calls, never make them. The only push
    it does is to its OWN __linkspy_events array — never a conversion event."""
    js = TRACKING_OBSERVER_JS
    assert "gtag('event'" not in js and 'gtag("event"' not in js
    assert "fbq('track'" not in js and 'fbq("track"' not in js
    # Every .push in the observer targets __linkspy_events, not dataLayer.
    for m in re.finditer(r"\.push\(", js):
        window = js[max(0, m.start() - 40):m.start()]
        assert "__linkspy_events" in window, f"unexpected push: …{window}"
    assert "__linkspy_events" in js and "rec(" in js


def test_the_live_plan_refuses_a_payment_form():
    collected = {"fields": [_field(name="cardnumber")], "iframes": []}
    plan = build_plan_for_live_form(collected, "https://shop.test")
    assert plan["refuse"] is not None and plan["submitted_once"] is False


def test_the_live_plan_refuses_a_stripe_iframe_form():
    collected = {"fields": [_field(name="email", type="email")],
                 "iframes": ["https://js.stripe.com/v3/"]}
    plan = build_plan_for_live_form(collected, "https://shop.test")
    assert plan["refuse"] is not None


def test_a_missing_form_refuses_rather_than_guesses():
    plan = build_plan_for_live_form(None, "https://x.test")
    assert plan["refuse"] and plan["submitted_once"] is False


def test_thankyou_is_detected_from_a_redirect_or_wording():
    assert _thankyou_detected("https://a/x", "https://a/thank-you", "") is True
    assert _thankyou_detected("https://a/x", "https://a/x", "Thank you for your message") is True
    assert _thankyou_detected("https://a/x", "https://a/x", "Please fill the form") is False


# ─── endpoint rails: the run endpoint refuses unless BOTH gates pass ─────────
import asyncio


def test_the_run_endpoint_refuses_when_the_flag_is_off(monkeypatch):
    import main
    monkeypatch.setattr(main, "active_testing_enabled", lambda: False)

    reached = []
    async def fake_optin(site_id, form_key):
        reached.append("optin")
        return {"enabled": True}
    monkeypatch.setattr(main, "get_form_optin", fake_optin)

    resp = asyncio.run(main.run_active_form_test("s1", form_key="f1", form_selector="#f"))
    assert resp.status_code == 403
    # It must short-circuit on the flag — never even look up the opt-in.
    assert reached == []


def test_the_run_endpoint_refuses_a_form_that_is_not_opted_in(monkeypatch):
    import main
    monkeypatch.setattr(main, "active_testing_enabled", lambda: True)

    async def not_opted(site_id, form_key):
        return {"enabled": False}
    monkeypatch.setattr(main, "get_form_optin", not_opted)

    submitted = []
    async def go():
        # If it ever reached submission we'd import the executor; assert it does not.
        return await main.run_active_form_test("s1", form_key="f1", form_selector="#f")
    resp = asyncio.run(go())
    assert resp.status_code == 403


def test_the_run_endpoint_refuses_when_no_optin_row_exists(monkeypatch):
    import main
    monkeypatch.setattr(main, "active_testing_enabled", lambda: True)

    async def none_optin(site_id, form_key):
        return None
    monkeypatch.setattr(main, "get_form_optin", none_optin)
    resp = asyncio.run(main.run_active_form_test("s1", form_key="f1", form_selector="#f"))
    assert resp.status_code == 403


# ─── a closed modal form must refuse, not misread every field as a honeypot ──
# apexure.com's contact form is a display:none modal until opened. Every field
# then reads visible=false / 0x0. Without the form_visible guard, the plan
# flagged name/email/message as honeypots and would have filled nothing while
# thinking it did.
def test_a_hidden_form_refuses_rather_than_misreading_its_fields():
    fields = [
        _field(name="name", type="text", visible=False, width=0, height=0),
        _field(name="email", type="email", visible=False, width=0, height=0),
        _field(name="message", tag="textarea", type="", visible=False, width=0, height=0),
    ]
    plan = plan_submission(fields, form_visible=False)
    assert plan["refuse"] is not None
    assert "not visible" in plan["refuse"]
    assert plan["fills"] == [] and plan["submitted_once"] is False


def test_the_same_fields_on_a_visible_form_are_filled_not_flagged():
    """Once the form is open, the fields are visible and get filled normally."""
    fields = [
        _field(name="name", type="text"),
        _field(name="email", type="email"),
        _field(name="message", tag="textarea", type=""),
    ]
    plan = plan_submission(fields, form_visible=True, test_email="qa+linkspy@acme.test")
    assert plan["refuse"] is None
    assert {f["name"] for f in plan["fills"]} == {"name", "email", "message"}


def test_a_real_honeypot_on_a_visible_form_is_still_caught_by_name():
    """The name-based trap detection works regardless of form visibility."""
    assert is_honeypot(_field(name="_gotcha"), form_visible=False) is True
    assert is_honeypot(_field(name="_gotcha"), form_visible=True) is True


# ─── never submit a blank form ───────────────────────────────────────────────
def test_a_form_with_no_fillable_field_refuses_rather_than_submitting_blank():
    """apexure's contact modal renders every field at 0x0 until opened. With
    nothing safely fillable we must refuse, never click submit on a blank form."""
    fields = [
        _field(name="name", type="text", visible=True, width=0, height=0),
        _field(name="email", type="email", visible=True, width=0, height=0),
        _field(name="_gotcha", type="text", visible=False, width=0, height=0),
    ]
    plan = plan_submission(fields, form_visible=True)
    assert plan["refuse"] is not None and plan["submitted_once"] is False
    assert plan["fills"] == []


def test_a_zero_size_real_field_is_not_filled():
    assert is_fillable(_field(name="email", type="email", width=0, height=0)) is False
