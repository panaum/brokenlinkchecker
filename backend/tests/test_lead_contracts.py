"""Contract-by-observation + drift validation — the definition of 'intact'."""
import pathlib

from lead_contracts import (draft_from_observation, validate_drift, detect_destination,
                            detect_events, is_attribution_field, contract_key)


def _form(fields, identifier="lead-form", action_url="", embed_scripts=(), index=0):
    return {"index": index, "identifier": identifier, "action_url": action_url,
            "embed_scripts": list(embed_scripts), "fields": fields}


def _f(name, type="text", required=False):
    return {"name": name, "type": type, "id": "", "placeholder": "", "required": required}


# ── draft-by-observation ──
def test_draft_matches_fixture_form_exactly():
    form = _form([
        _f("email", "email", required=True),
        _f("firstname", required=True),
        _f("gclid", "hidden"),
        _f("utm_source", "hidden"),
    ], action_url="https://api.hsforms.com/submissions/v3/integration/submit/2401/abc")
    hydrated = {"gclid": "lspy-test", "utm_source": "lspy-test"}  # JS populated from URL
    c = draft_from_observation(form, "https://x.com/contact", hydrated_values=hydrated)

    assert c["status"] == "draft"
    by = {f["name"]: f for f in c["fields"]}
    assert by["email"]["kind"] == "visible" and by["email"]["populated_by"] == "user"
    assert by["email"]["required"] is True and by["email"]["expected_crm_property"] == "email"
    assert by["firstname"]["expected_crm_property"] == "firstname"
    # hidden inputs that carried a value after hydration are JS-populated
    assert by["gclid"]["kind"] == "hidden" and by["gclid"]["populated_by"] == "js"
    assert by["utm_source"]["populated_by"] == "js"
    assert c["form_ref"]["page_url"] == "https://x.com/contact"


def test_hidden_field_not_populated_is_static_not_js():
    form = _form([_f("email", "email"), _f("empty_hidden", "hidden")])
    c = draft_from_observation(form, "https://x.com", hydrated_values={})  # nothing hydrated
    hidden = next(f for f in c["fields"] if f["name"] == "empty_hidden")
    assert hidden["populated_by"] == "static"   # present but never populated → not a JS tracker


def test_unnamed_fields_are_dropped():
    c = draft_from_observation(_form([_f(""), _f("email", "email")]), "https://x.com")
    assert [f["name"] for f in c["fields"]] == ["email"]


# ── destination detection ──
def test_detect_hubspot_and_ghl_and_webhook_and_unknown():
    hs = detect_destination(embed_attrs='portalId: 2401, formId: 0a1b2c3d-4e5f-6789-abcd-ef0123456789',
                            embed_scripts=["https://js.hsforms.net/forms/embed/v2.js"])
    assert hs["type"] == "hubspot" and hs["ids"]["portal_id"] == "2401"
    ghl = detect_destination(scripts_text="https://link.msgsndr.com/form/abc123")
    assert ghl["type"] == "ghl"
    wh = detect_destination(action_url="https://hooks.example.com/lead")
    assert wh["type"] == "webhook"
    assert detect_destination()["type"] == "unknown"    # no evidence → never guessed


def test_detect_lead_events_only():
    txt = "gtag('event','generate_lead'); fbq('track','Lead'); gtag('event','page_view');"
    events = detect_events(txt)
    names = {e["name"] for e in events}
    assert "generate_lead" in names and "Lead" in names
    assert "page_view" not in names   # not conversion-ish


def test_attribution_field_matcher():
    assert is_attribution_field("gclid") and is_attribution_field("utm_medium")
    assert is_attribution_field("fbclid") and not is_attribution_field("email")


# ── drift, per class ──
def _contract(fields, destination=None):
    return {"fields": fields, "destination": destination or {"type": "hubspot", "ids": {"portal_id": "2401"}}}


def test_drift_field_removed():
    c = _contract([{"name": "email", "kind": "visible", "required": True, "populated_by": "user"}])
    obs = _form([_f("firstname")])   # email gone
    v = validate_drift(c, obs)
    assert len(v) == 1 and v[0]["kind"] == "field_removed" and v[0]["severity"] == "high"


def test_drift_dead_js_population_of_attribution_field_is_high():
    c = _contract([{"name": "gclid", "kind": "hidden", "populated_by": "js", "required": False}])
    obs = _form([_f("gclid", "hidden")])
    v = validate_drift(c, obs, hydrated_values={})    # gclid no longer populated
    assert v[0]["kind"] == "not_populated" and v[0]["severity"] == "high"
    assert "unattributable" in v[0]["consequence"]


def test_drift_destination_swap_is_critical():
    c = _contract([{"name": "email", "kind": "visible", "required": False, "populated_by": "user"}],
                  destination={"type": "hubspot", "ids": {"portal_id": "2401"}})
    obs = _form([_f("email", "email")], action_url="https://hooks.evil.com/x")
    v = validate_drift(c, obs)
    swap = [x for x in v if x["kind"] == "destination_changed"]
    assert swap and swap[0]["severity"] == "critical"


def test_drift_required_flag_change():
    c = _contract([{"name": "email", "kind": "visible", "required": True, "populated_by": "user"}])
    obs = _form([_f("email", "email", required=False)])
    v = validate_drift(c, obs)
    assert any(x["kind"] == "required_drift" for x in v)


def test_no_drift_when_form_matches_contract():
    c = _contract([{"name": "email", "kind": "visible", "required": True, "populated_by": "user"},
                   {"name": "gclid", "kind": "hidden", "populated_by": "js", "required": False}])
    obs = _form([_f("email", "email", required=True), _f("gclid", "hidden")],
                action_url="", embed_scripts=["https://js.hsforms.net/forms/embed/v2.js"])
    # match destination by giving the same hubspot signal
    obs["identifier"] = "portalId: 2401"
    v = validate_drift(c, obs, hydrated_values={"gclid": "lspy-test"})
    assert v == []


# ── the moat: ledger append-only enforcement lives in the migration ──
def test_ledger_migration_enforces_append_only():
    sql = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "013_lead_contracts.sql").read_text(encoding="utf-8")
    assert "tracer_runs" in sql
    # a DB trigger — not just app code — must block DELETE and non-cleanup UPDATE
    assert "before update or delete on tracer_runs" in sql
    assert "append-only" in sql.lower()
    assert "cleanup done" in sql.lower()   # closed rows are frozen
