"""Google Ads CSV parse — defensive against the mess of real exports."""
from ads_import import parse_ads_csv, _parse_cost


def test_clean_export_parses():
    csv = (
        "Campaign,Ad group,Final URL,Cost\n"
        "Brand,Core,https://apexure.com/pricing,12.50\n"
        "Brand,Core,https://apexure.com/book,8\n"
        "Leadgen,Quote,https://apexure.com/quote,3.20\n"
    )
    r = parse_ads_csv(csv)
    assert r["count"] == 3
    assert r["has_cost"] is True
    assert set(r["campaigns"]) == {"Brand", "Leadgen"}
    assert r["destinations"][0]["cost_per_day"] == 12.50


def test_skips_google_preamble_and_totals():
    csv = (
        "Campaign report (Jun 1 2026 - Jun 30 2026)\n"
        "\n"
        "Campaign,Ad group,Final URL\n"
        "Brand,Core,https://apexure.com/a\n"
        " Total: account,,\n"          # junk total row → no URL, skipped
        ",,\n"                          # blank-ish
    )
    r = parse_ads_csv(csv)
    assert r["count"] == 1
    assert r["destinations"][0]["final_url"] == "https://apexure.com/a"
    assert r["skipped"] >= 1


def test_quoted_url_with_commas_and_dedup():
    csv = (
        'Campaign,Final URL\n'
        '"Brand, EU","https://apexure.com/x?a=1,2,3"\n'
        '"Brand, EU","https://apexure.com/x?a=1,2,3"\n'   # exact dup
    )
    r = parse_ads_csv(csv)
    assert r["count"] == 1
    assert r["destinations"][0]["campaign"] == "Brand, EU"
    assert "1,2,3" in r["destinations"][0]["final_url"]


def test_locale_decimal_comma_cost():
    assert _parse_cost("1.234,56") == 1234.56   # de-DE
    assert _parse_cost("1,234.56") == 1234.56   # en-US
    assert _parse_cost("€ 12,50") == 12.50
    assert _parse_cost("$8") == 8.0
    assert _parse_cost("--") is None
    assert _parse_cost("") is None


def test_missing_cost_column_hides_spend():
    csv = "Campaign,Final URL\nBrand,https://apexure.com/a\n"
    r = parse_ads_csv(csv)
    assert r["count"] == 1
    assert r["has_cost"] is False
    assert any("spend figures will be hidden" in w for w in r["warnings"])


def test_no_final_url_column_is_a_clear_error():
    csv = "Campaign,Clicks,Impressions\nBrand,10,1000\n"
    r = parse_ads_csv(csv)
    assert r["count"] == 0
    assert any("Final URL" in w for w in r["warnings"])


def test_bare_domain_and_template_urls():
    csv = (
        "Campaign,Final URL\n"
        "Brand,apexure.com/pricing\n"       # bare domain → https:// prefixed
        "Brand,{lpurl}\n"                    # template → skipped
        "Brand,--\n"                         # none → skipped
    )
    r = parse_ads_csv(csv)
    assert r["count"] == 1
    assert r["destinations"][0]["final_url"] == "https://apexure.com/pricing"


def test_empty_input():
    r = parse_ads_csv("")
    assert r["count"] == 0 and r["destinations"] == []
