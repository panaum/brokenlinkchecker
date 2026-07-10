"""
Fix Pack.

Everything in the pack derives from scanned page content. Anchor text is
attacker-controlled: it lands in a spreadsheet the client opens and a markdown
file they read. `=HYPERLINK("http://evil","Click")` as an anchor text becomes a
live link in the client's Excel unless every cell is neutralised.
"""
import csv
import io
import zipfile

import pytest

from fix_pack import (
    CSV_COLUMNS,
    build_fix_pack,
    build_rows,
    csv_safe,
    fixes_csv,
    instructions_md,
    md_safe,
    md_url,
)


SITE = "https://acme.test"


def _finding(**over) -> dict:
    base = {
        "fingerprint": "fp1", "url": "https://acme.test/gone", "anchor_text": "Buy Now",
        "bucket": "broken", "resource_type": "anchor", "is_external": False,
        "status_code": 404, "page_url": "https://acme.test/pricing",
        "redirect_chain": [], "redirect_flags": [],
    }
    base.update(over)
    return base


# ─── CSV injection ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("payload", [
    '=HYPERLINK("http://evil.test","Click me")',
    '=1+1',
    '+1234567890',
    '-2+3+cmd|\' /C calc\'!A0',
    '@SUM(1+1)',
    '\t=1+1',          # a tab a spreadsheet strips before parsing
    '\r=1+1',
])
def test_formula_payloads_are_neutralised(payload):
    cell = csv_safe(payload)
    assert not cell.startswith(("=", "+", "-", "@")), cell
    assert cell.startswith("'")


def test_ordinary_values_are_untouched():
    assert csv_safe("Buy Now") == "Buy Now"
    assert csv_safe("https://acme.test/x") == "https://acme.test/x"
    assert csv_safe(404) == "404"
    assert csv_safe(None) == ""


def test_newlines_never_break_out_of_a_cell():
    assert "\n" not in csv_safe("a\nb")
    assert "\r" not in csv_safe("a\rb")


def test_a_malicious_anchor_text_reaches_the_csv_neutralised():
    rows = build_rows([_finding(anchor_text='=HYPERLINK("http://evil.test","x")')],
                      "Elementor", SITE)
    body = fixes_csv(rows)
    parsed = list(csv.DictReader(io.StringIO(body)))
    assert parsed[0]["element"].startswith("'=HYPERLINK")


def test_csv_has_a_row_per_finding_and_the_declared_columns():
    rows = build_rows([_finding(), _finding(url="https://acme.test/two")],
                      "Elementor", SITE)
    parsed = list(csv.DictReader(io.StringIO(fixes_csv(rows))))
    assert len(parsed) == 2
    assert list(parsed[0]) == CSV_COLUMNS


def test_csv_records_the_template_that_produced_the_fix():
    rows = build_rows([_finding()], "Elementor", SITE)
    parsed = list(csv.DictReader(io.StringIO(fixes_csv(rows))))
    assert parsed[0]["template_source"] == "fix_templates/elementor.yaml"


# ─── markdown escaping ───────────────────────────────────────────────────────
def test_md_safe_escapes_structure_characters():
    escaped = md_safe("a|b `code` <img> #head *em*")
    for ch in ("|", "`", "<", ">", "#", "*"):
        assert f"\\{ch}" in escaped


def test_md_url_wraps_and_strips_newlines():
    assert md_url("https://acme.test/x") == "<https://acme.test/x>"
    assert "\n" not in md_url("https://acme.test/\nx")


def test_malicious_anchor_cannot_inject_html_into_instructions():
    rows = build_rows([_finding(anchor_text='<script>alert(1)</script>')],
                      "Elementor", SITE)
    body = instructions_md(rows, site_url=SITE, builder="Elementor")
    assert "<script>" not in body
    assert r"\<script\>" in body


def test_instructions_group_by_page_then_issue():
    rows = build_rows([
        _finding(page_url="https://acme.test/a", url="https://acme.test/x"),
        _finding(page_url="https://acme.test/b", url="https://acme.test/y",
                 bucket="dead_cta"),
    ], "Elementor", SITE)
    body = instructions_md(rows, site_url=SITE, builder="Elementor")
    assert "## https://acme.test/a" in body.replace("\\", "")
    assert "## https://acme.test/b" in body.replace("\\", "")
    assert "### Broken links" in body
    assert "### Buttons that go nowhere" in body


def test_instructions_state_when_no_replacement_is_suggested():
    body = instructions_md(build_rows([_finding()], "Elementor", SITE),
                           site_url=SITE, builder="Elementor")
    assert "needs a human decision" in body


def test_instructions_never_leave_a_stray_placeholder():
    rows = build_rows([_finding(), _finding(bucket="dead_cta")], "Elementor", SITE)
    body = instructions_md(rows, site_url=SITE, builder="Elementor")
    assert "{" not in body and "}" not in body


def test_instructions_disclaim_the_suggested_value():
    rows = build_rows([_finding(redirect_chain=[
        {"url": "https://acme.test/gone", "status": 301},
        {"url": "https://acme.test/new", "status": 404}])], "Elementor", SITE)
    body = instructions_md(rows, site_url=SITE, builder="Elementor")
    assert "confirm before applying" in body.lower()


def test_empty_pack_says_so():
    body = instructions_md([], site_url=SITE, builder="Elementor")
    assert "Nothing to fix" in body


def test_instructions_declare_no_llm_was_used():
    body = instructions_md(build_rows([_finding()], "", SITE), site_url=SITE, builder="")
    assert "language model" in body.lower()


# ─── the zip ─────────────────────────────────────────────────────────────────
def test_zip_contains_the_expected_members():
    rows = build_rows([_finding()], "Elementor", SITE)
    blob = build_fix_pack(rows, site_url=SITE, builder="Elementor", redirect_rules=[
        {"from": "https://acme.test/old", "to": "https://acme.test/new",
         "status": 301, "hops": 1},
    ])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
    assert {"README.txt", "fixes.csv", "instructions.md"} <= names
    assert any(n.startswith("redirects/") for n in names)


def test_zip_omits_redirects_when_there_are_none():
    blob = build_fix_pack(build_rows([_finding()], "", SITE), site_url=SITE, builder="")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert not any(n.startswith("redirects/") for n in zf.namelist())


def test_zip_drops_poisoned_redirect_rules():
    blob = build_fix_pack(build_rows([_finding()], "", SITE), site_url=SITE, builder="",
                          redirect_rules=[{"from": "javascript:alert(1)",
                                           "to": "https://acme.test/x",
                                           "status": 301, "hops": 1}])
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert not any(n.startswith("redirects/") for n in zf.namelist())


def test_zip_is_readable_and_utf8():
    rows = build_rows([_finding(anchor_text="Réserver — 予約")], "", SITE)
    blob = build_fix_pack(rows, site_url=SITE, builder="")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        body = zf.read("instructions.md").decode("utf-8")
    assert "Réserver" in body
