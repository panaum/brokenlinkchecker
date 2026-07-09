"""
Redirect forensics + ruleset generation.

The security half matters most: every URL in a generated rule came from scanned
page content and is untrusted (hard constraint 4). A URL carrying a newline
would otherwise inject an arbitrary directive into an .htaccess file.
"""
import asyncio

import httpx
import pytest

from checker import build_redirect_chain, check_single
from models import RawLink
from redirect_rules import (
    FLAG_HTTP_TO_HTTPS,
    FLAG_LONG_CHAIN,
    FLAG_LOOP,
    FLAG_SLASH_BOUNCE,
    MAX_REDIRECT_HOPS,
    analyze_chain,
    classify_redirect,
    collapse_chain,
    collapse_rules,
    is_safe_url,
    is_scheme_upgrade,
    redirect_summary,
    render,
    sanitize_rules,
    to_cloudflare_csv,
    to_htaccess,
    to_netlify,
)


def _hop(url, status=301):
    return {"url": url, "status": status}


# ─── analyze_chain ───────────────────────────────────────────────────────────
def test_direct_hit_has_no_flags():
    assert analyze_chain([]) == []
    assert analyze_chain([_hop("https://a.test/x", 200)]) == []


def test_short_chain_is_not_flagged_long():
    chain = [_hop("https://a.test/1"), _hop("https://a.test/2", 200)]
    assert FLAG_LONG_CHAIN not in analyze_chain(chain)


def test_three_hops_is_a_long_chain():
    chain = [_hop("https://a.test/1"), _hop("https://a.test/2"),
             _hop("https://a.test/3"), _hop("https://a.test/4", 200)]
    assert FLAG_LONG_CHAIN in analyze_chain(chain)


def test_http_to_https_hop_is_flagged():
    chain = [_hop("http://a.test/x"), _hop("https://a.test/x", 200)]
    assert FLAG_HTTP_TO_HTTPS in analyze_chain(chain)


def test_slash_bounce_is_flagged():
    chain = [_hop("https://a.test/x"), _hop("https://a.test/x/", 200)]
    assert FLAG_SLASH_BOUNCE in analyze_chain(chain)


def test_loop_is_detected():
    chain = [_hop("https://a.test/x"), _hop("https://a.test/y"),
             _hop("https://a.test/x", 200)]
    assert FLAG_LOOP in analyze_chain(chain)


def test_slash_only_loop_is_detected():
    """/a -> /a/ -> /a never settles."""
    chain = [_hop("https://a.test/a"), _hop("https://a.test/a/"),
             _hop("https://a.test/a", 200)]
    assert FLAG_LOOP in analyze_chain(chain)


# ─── classify_redirect ───────────────────────────────────────────────────────
@pytest.mark.parametrize("status,expected", [
    (301, "permanent"), (308, "permanent"),
    (302, "temporary"), (303, "temporary"), (307, "temporary"),
])
def test_classify_redirect(status, expected):
    chain = [_hop("https://a.test/1", status), _hop("https://a.test/2", 200)]
    assert classify_redirect(chain) == expected


def test_classify_redirect_none_for_direct_hit():
    assert classify_redirect([_hop("https://a.test/x", 200)]) == "none"


# ─── collapse_chain ──────────────────────────────────────────────────────────
def test_collapse_chain_maps_first_hop_to_final_destination():
    chain = [_hop("https://a.test/old", 301), _hop("https://a.test/mid", 302),
             _hop("https://a.test/new", 200)]
    rule = collapse_chain(chain)
    assert rule["from"] == "https://a.test/old"
    assert rule["to"] == "https://a.test/new"
    assert rule["status"] == 301          # first hop was permanent
    assert rule["hops"] == 2


def test_collapse_chain_uses_302_for_a_temporary_first_hop():
    chain = [_hop("https://a.test/old", 302), _hop("https://a.test/new", 200)]
    assert collapse_chain(chain)["status"] == 302


def test_collapse_chain_refuses_a_loop():
    """A loop has no stable destination to point a rule at."""
    chain = [_hop("https://a.test/x"), _hop("https://a.test/y"),
             _hop("https://a.test/x", 200)]
    assert collapse_chain(chain) is None


def test_collapse_chain_refuses_a_direct_hit():
    assert collapse_chain([_hop("https://a.test/x", 200)]) is None


def test_collapse_chain_refuses_an_unsafe_endpoint():
    chain = [_hop('https://a.test/"evil'), _hop("https://a.test/new", 200)]
    assert collapse_chain(chain) is None


def test_collapse_rules_dedupes_and_sorts():
    results = [
        {"redirect_chain": [_hop("https://a.test/b"), _hop("https://a.test/z", 200)]},
        {"redirect_chain": [_hop("https://a.test/a"), _hop("https://a.test/z", 200)]},
        {"redirect_chain": [_hop("https://a.test/b"), _hop("https://a.test/z", 200)]},
    ]
    rules = collapse_rules(results)
    assert [r["from"] for r in rules] == ["https://a.test/a", "https://a.test/b"]


# ─── deployable rules: same-origin, no scheme upgrades ───────────────────────
# Regression (found running Phase 3 against real URLs): collapsing external
# redirects produced
#     Redirect 301 / https://github.com/
#     Redirect 301 / https://astro.build/
# because _redirects and .htaccess address the source by PATH. Deploying that
# would point the site's own homepage at someone else's.
def test_external_redirects_are_not_deployable_rules():
    results = [{"redirect_chain": [_hop("http://github.com", 301),
                                   _hop("https://github.com/", 200)]}]
    assert collapse_rules(results, site_url="https://acme.test/") == []


def test_own_site_redirects_are_kept():
    results = [{"redirect_chain": [_hop("https://acme.test/old", 301),
                                   _hop("https://acme.test/new", 200)]}]
    rules = collapse_rules(results, site_url="https://acme.test/")
    assert [r["from"] for r in rules] == ["https://acme.test/old"]


@pytest.mark.parametrize("source,target", [
    ("http://acme.test/p", "https://acme.test/p"),
    ("http://acme.test/p", "https://acme.test/p/"),
    ("http://acme.test/", "https://acme.test/"),
])
def test_scheme_upgrades_are_excluded(source, target):
    """`Redirect 301 /p https://acme.test/p` also fires for the https request —
    the site would redirect to itself forever."""
    assert is_scheme_upgrade(source, target) is True
    results = [{"redirect_chain": [_hop(source, 301), _hop(target, 200)]}]
    assert collapse_rules(results, site_url="https://acme.test/") == []


def test_a_real_path_change_over_https_is_not_a_scheme_upgrade():
    assert is_scheme_upgrade("http://acme.test/old", "https://acme.test/new") is False


def test_two_rules_never_share_a_source_path_in_path_based_formats():
    """Defence in depth: a duplicate path would silently shadow a rule."""
    colliding = [
        {"from": "https://a.test/", "to": "https://a.test/x", "status": 301, "hops": 1},
        {"from": "https://b.test/", "to": "https://b.test/y", "status": 301, "hops": 1},
    ]
    body = to_htaccess(colliding)
    assert body.count("  Redirect 301 /") == 1
    assert to_netlify(colliding).count("/  https://") == 1


# ─── is_safe_url: untrusted scanned content ──────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://a.test/ok",
    "http://a.test/ok?x=1",
    "https://a.test/ok#frag",
])
def test_safe_urls_pass(url):
    assert is_safe_url(url) is True


@pytest.mark.parametrize("url", [
    'https://a.test/"quote',                       # breaks a CSV field
    "https://a.test/'quote",
    "https://a.test/new\nRedirect 301 /x /evil",   # injects an .htaccess directive
    "https://a.test/new\r\nHeader set X: y",
    "https://a.test/has space",                    # breaks _redirects columns
    "https://a.test/tab\there",
    "https://a.test/null\x00byte",
    "javascript:alert(1)",
    "data:text/html,<script>",
    "file:///etc/passwd",
    "//protocol-relative.test/x",
    "https://good.test@evil.test/x",               # host-spoofing via userinfo
    "not a url",
    "",
    None,
    12345,
    "https://a.test/" + "x" * 3000,                # absurd length
])
def test_unsafe_urls_are_rejected(url):
    assert is_safe_url(url) is False


# ─── rule rendering: escaping per format ─────────────────────────────────────
RULES = [
    {"from": "https://a.test/old", "to": "https://a.test/new", "status": 301, "hops": 1},
    {"from": "https://a.test/x?q=1", "to": "https://b.test/y", "status": 302, "hops": 2},
]


def test_cloudflare_csv_has_a_header_and_a_row_per_rule():
    body = to_cloudflare_csv(RULES)
    lines = body.strip().split("\n")
    assert lines[0] == "source,target,status,preserve_query_string"
    assert len(lines) == 3
    assert "https://a.test/old" in lines[1]


def test_netlify_uses_paths_for_the_source():
    body = to_netlify(RULES)
    assert "/old  https://a.test/new  301!" in body
    assert "/x?q=1  https://b.test/y  302!" in body


def test_htaccess_wraps_directives_in_ifmodule():
    body = to_htaccess(RULES)
    assert body.startswith("# Generated by LinkSpy")
    assert "<IfModule mod_alias.c>" in body
    assert "  Redirect 301 /old https://a.test/new" in body
    assert "</IfModule>" in body


@pytest.mark.parametrize("fmt", ["cloudflare", "netlify", "htaccess"])
def test_no_generated_line_ever_contains_a_newline_from_a_url(fmt):
    """An injected rule must be dropped, not escaped-and-emitted."""
    poisoned = [{"from": "https://a.test/x\nRedirect 301 /a /evil",
                 "to": "https://a.test/y", "status": 301, "hops": 1}]
    _media, _name, body = render(fmt, poisoned)
    assert "/evil" not in body


@pytest.mark.parametrize("fmt", ["cloudflare", "netlify", "htaccess"])
def test_render_drops_unsafe_rules_but_keeps_safe_ones(fmt):
    mixed = RULES + [{"from": 'https://a.test/"x', "to": "https://a.test/y",
                      "status": 301, "hops": 1}]
    _media, _name, body = render(fmt, mixed)
    assert "https://a.test/new" in body
    assert '"x' not in body


def test_sanitize_rules_defaults_a_bogus_status():
    cleaned = sanitize_rules([{"from": "https://a.test/a", "to": "https://a.test/b",
                               "status": 999}])
    assert cleaned[0]["status"] == 301


def test_sanitize_rules_drops_unsafe_endpoints():
    assert sanitize_rules([{"from": "javascript:alert(1)", "to": "https://a.test/b",
                            "status": 301}]) == []


def test_render_rejects_an_unknown_format():
    with pytest.raises(KeyError):
        render("php", RULES)


# ─── redirect_summary ────────────────────────────────────────────────────────
def test_redirect_summary_counts_permanent_and_temporary():
    results = [
        {"redirect_chain": [_hop("https://a.test/1", 301), _hop("https://a.test/2", 200)],
         "redirect_flags": []},
        {"redirect_chain": [_hop("https://a.test/3", 302), _hop("https://a.test/4", 200)],
         "redirect_flags": [FLAG_HTTP_TO_HTTPS]},
        {"redirect_chain": [], "redirect_flags": []},
    ]
    summary = redirect_summary(results)
    assert summary["permanent"] == 1
    assert summary["temporary"] == 1
    assert summary["total"] == 2
    assert summary["flags"][FLAG_HTTP_TO_HTTPS] == 1
    assert summary["collapsible_rules"] == 2


# ─── through the checker ─────────────────────────────────────────────────────
def _raw(url="https://acme.test/start") -> RawLink:
    return RawLink(url=url, source_element="a", anchor_text="x",
                   category="Body text", is_external=False)


def _run(handler, link=None):
    async def go():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True,
                                     max_redirects=MAX_REDIRECT_HOPS) as client:
            return await check_single(client, link or _raw())
    return asyncio.run(go())


def test_checker_records_the_hop_chain():
    def handler(request):
        path = request.url.path
        if path == "/start":
            return httpx.Response(301, headers={"Location": "https://acme.test/mid"})
        if path == "/mid":
            return httpx.Response(302, headers={"Location": "https://acme.test/end"})
        return httpx.Response(200)

    result = _run(handler)
    assert [h["url"] for h in result.redirect_chain] == [
        "https://acme.test/start", "https://acme.test/mid", "https://acme.test/end",
    ]
    assert result.label == "ok"
    assert result.bucket == "ok"


def test_redirect_chain_is_empty_for_a_direct_hit():
    result = _run(lambda req: httpx.Response(200))
    assert result.redirect_chain == []
    assert result.redirect_flags == []


def test_a_redirect_is_never_broken():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(301, headers={"Location": "https://acme.test/end"})
        return httpx.Response(200)

    result = _run(handler)
    assert result.bucket == "ok"


def test_redirect_loop_is_unverifiable_not_broken():
    """Capped at MAX_REDIRECT_HOPS. A loop means we never reached a destination —
    it does not prove the link is broken."""
    def handler(request):
        nxt = "https://acme.test/b" if request.url.path == "/a" else "https://acme.test/a"
        return httpx.Response(302, headers={"Location": nxt})

    result = _run(handler, _raw("https://acme.test/a"))
    assert result.label == "redirect"
    assert result.bucket == "unverifiable"
    assert FLAG_LOOP in result.redirect_flags
    assert "loop" in result.error.lower()
    assert str(MAX_REDIRECT_HOPS) in result.error


def test_build_redirect_chain_ignores_a_single_response():
    response = httpx.Response(200, request=httpx.Request("GET", "https://a.test/x"))
    assert build_redirect_chain(response) == []
