"""
Redirect forensics and ruleset generation.

Two jobs:

1. Analyze the hop chain a link actually took (the checker already follows
   redirects) and classify it — long chain, http->https, slash bounce, loop.
   These are *informational*. A redirect is not a broken link.

2. Emit a collapsed ruleset (first hop -> final destination) as Cloudflare Bulk
   Redirects CSV, a Netlify _redirects file, or Apache .htaccess.

SECURITY (hard constraint 4): every URL in a rule originates from scanned page
content and is therefore untrusted. It must pass strict validation before it can
appear in a generated artifact, and it must be escaped for that artifact's
format. A URL containing a newline could otherwise inject an arbitrary directive
into an .htaccess file.
"""
import csv
import io
from typing import Optional
from urllib.parse import urlsplit

# The checker stops following after this many hops and calls it a loop.
MAX_REDIRECT_HOPS = 10

# A chain with at least this many hops is worth collapsing.
LONG_CHAIN_HOPS = 3

PERMANENT_STATUSES = frozenset({301, 308})
TEMPORARY_STATUSES = frozenset({302, 303, 307})

# Flags attached to a redirect chain. Informational only — never a bucket.
FLAG_LONG_CHAIN = "long_chain"
FLAG_HTTP_TO_HTTPS = "http_to_https"
FLAG_SLASH_BOUNCE = "slash_bounce"
FLAG_LOOP = "loop"

# Characters that would let scanned content escape the line it belongs on.
# Space is included: no rule format quotes it safely in every position, and a
# URL with a raw space is invalid anyway.
_FORBIDDEN_CHARS = set('\r\n\t\x00"\'\\ <>`')


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────
def is_safe_url(url) -> bool:
    """Strict: an absolute http(s) URL with a host, and no character that could
    break out of a CSV field, a _redirects line, or an .htaccess directive."""
    if not url or not isinstance(url, str):
        return False
    if len(url) > 2000:
        return False
    if any(ch in _FORBIDDEN_CHARS for ch in url):
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    if not parts.netloc:
        return False
    # A stray "@" can disguise the real host: https://good.test@evil.test/
    if "@" in parts.netloc:
        return False
    return True


def _path_of(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


# ─────────────────────────────────────────────────────────────────────────────
# Chain analysis
# ─────────────────────────────────────────────────────────────────────────────
def analyze_chain(chain: list) -> list:
    """Flags for a hop chain [{"url", "status"}, …] ending at the final URL.

    A direct hit (0 or 1 entries) has no flags.
    """
    if not chain or len(chain) < 2:
        return []

    flags = []
    urls = [hop.get("url", "") for hop in chain]

    # Entries, not hops: 4 entries is 3 redirects.
    if len(chain) - 1 >= LONG_CHAIN_HOPS:
        flags.append(FLAG_LONG_CHAIN)

    for before, after in zip(urls, urls[1:]):
        if before.startswith("http://") and after.startswith("https://"):
            if FLAG_HTTP_TO_HTTPS not in flags:
                flags.append(FLAG_HTTP_TO_HTTPS)
        # Slash bounce: the same resource with and without its trailing slash.
        if before != after and before.rstrip("/") == after.rstrip("/"):
            if FLAG_SLASH_BOUNCE not in flags:
                flags.append(FLAG_SLASH_BOUNCE)

    # A genuine loop revisits an EXACT URL — a cycle returns to a node it has
    # already visited (e.g. /a -> /a/ -> /a, where /a repeats). Compare exact
    # URLs, NOT slash-normalized ones: /x and /x/ are distinct resources, so a
    # terminating bounce /x -> /x/ (200) settles and must not read as a loop.
    seen = set()
    for url in urls:
        if url in seen:
            flags.append(FLAG_LOOP)
            break
        seen.add(url)

    return flags


def classify_redirect(chain: list) -> str:
    """'permanent' | 'temporary' | 'none' — drives the Redirects panel."""
    if not chain or len(chain) < 2:
        return "none"
    status = chain[0].get("status")
    if status in PERMANENT_STATUSES:
        return "permanent"
    if status in TEMPORARY_STATUSES:
        return "temporary"
    return "none"


def collapse_chain(chain: list) -> Optional[dict]:
    """Collapse a chain to a single rule: first hop -> final destination.

    Returns None when there is nothing to collapse (no redirect), when the chain
    loops (there is no stable destination to point at), or when either endpoint
    fails validation.
    """
    if not chain or len(chain) < 2:
        return None
    if FLAG_LOOP in analyze_chain(chain):
        return None

    source = chain[0].get("url", "")
    target = chain[-1].get("url", "")
    if not is_safe_url(source) or not is_safe_url(target):
        return None
    if source == target:
        return None

    return {
        "from": source,
        "to": target,
        "status": 301 if chain[0].get("status") in PERMANENT_STATUSES else 302,
        "hops": len(chain) - 1,
    }


def _same_host(a: str, b: str) -> bool:
    return urlsplit(a).netloc.lower() == urlsplit(b).netloc.lower()


def is_scheme_upgrade(source: str, target: str) -> bool:
    """http://x/p -> https://x/p. Infrastructure, not a content fix.

    Emitting it as a path-based rule is actively harmful: `Redirect 301 /p https://x/p`
    fires for the https request too, and the site redirects to itself forever.
    """
    s, t = urlsplit(source), urlsplit(target)
    return (
        s.scheme == "http" and t.scheme == "https"
        and s.netloc.lower() == t.netloc.lower()
        and s.path.rstrip("/") == t.path.rstrip("/")
        and s.query == t.query
    )


def collapse_rules(results, site_url: str = "") -> list:
    """Deployable rules: one per distinct source URL, sorted for a stable file.

    Only redirects that START on the scanned site are included. Netlify's
    _redirects and .htaccess address sources by PATH, so a rule collapsed from
    an external link (http://github.com -> https://github.com/) would render as
    `Redirect 301 / https://github.com/` and point the site's own homepage at
    someone else's. A redirect on an external link is not ours to fix anyway.
    """
    rules: dict = {}
    for result in results or []:
        chain = _get(result, "redirect_chain") or []
        rule = collapse_chain(chain)
        if not rule:
            continue
        if is_scheme_upgrade(rule["from"], rule["to"]):
            continue
        if site_url and not _same_host(rule["from"], site_url):
            continue
        if rule["from"] not in rules:
            rules[rule["from"]] = rule
    return sorted(rules.values(), key=lambda r: r["from"])


def _get(result, field):
    if isinstance(result, dict):
        return result.get(field)
    return getattr(result, field, None)


# ─────────────────────────────────────────────────────────────────────────────
# Ruleset formats
#
# Every emitted line is built from URLs that already passed is_safe_url(), so
# they contain no quotes, whitespace, or control characters. Each writer still
# escapes for its own format rather than relying on that — defence in depth.
# ─────────────────────────────────────────────────────────────────────────────
def to_cloudflare_csv(rules: list) -> str:
    """Cloudflare Bulk Redirects. csv writer quotes and doubles any quote."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["source", "target", "status", "preserve_query_string"])
    for rule in rules:
        writer.writerow([rule["from"], rule["to"], rule["status"], "true"])
    return out.getvalue()


def _by_unique_source_path(rules: list):
    """Path-addressed formats cannot hold two rules for one source path.

    collapse_rules() already restricts sources to a single host, so a collision
    should not occur — but a duplicate here would silently shadow a rule, so
    drop it rather than emit an ambiguous file.
    """
    seen = set()
    for rule in rules:
        path = _path_of(rule["from"])
        if path in seen:
            continue
        seen.add(path)
        yield rule, path


def to_netlify(rules: list) -> str:
    """Netlify _redirects: `from  to  status`, whitespace-separated."""
    lines = ["# Generated by LinkSpy — collapsed redirect chains"]
    for rule, path in _by_unique_source_path(rules):
        lines.append(f"{path}  {rule['to']}  {rule['status']}!")
    return "\n".join(lines) + "\n"


def to_htaccess(rules: list) -> str:
    """Apache .htaccess Redirect directives."""
    lines = [
        "# Generated by LinkSpy — collapsed redirect chains",
        "<IfModule mod_alias.c>",
    ]
    for rule, path in _by_unique_source_path(rules):
        lines.append(f"  Redirect {rule['status']} {path} {rule['to']}")
    lines.append("</IfModule>")
    return "\n".join(lines) + "\n"


FORMATS = {
    "cloudflare": ("text/csv", "linkspy-redirects.csv", to_cloudflare_csv),
    "netlify": ("text/plain", "_redirects", to_netlify),
    "htaccess": ("text/plain", ".htaccess", to_htaccess),
}


def sanitize_rules(rules: list) -> list:
    """Drop any rule whose endpoints do not pass validation.

    Rules are persisted between scans, so by the time they are rendered they are
    data from storage rather than data we just validated. Re-check instead of
    trusting the round trip — the source is still scanned page content.
    """
    clean = []
    for rule in rules or []:
        source, target = rule.get("from"), rule.get("to")
        if not is_safe_url(source) or not is_safe_url(target):
            continue
        status = rule.get("status")
        if status not in PERMANENT_STATUSES and status not in TEMPORARY_STATUSES:
            status = 301
        clean.append({"from": source, "to": target, "status": status,
                      "hops": rule.get("hops", 1)})
    return clean


def render(fmt: str, rules: list) -> tuple:
    """(media_type, filename, body). Raises KeyError on an unknown format."""
    media_type, filename, writer = FORMATS[fmt]
    return media_type, filename, writer(sanitize_rules(rules))


def redirect_summary(results, site_url: str = "") -> dict:
    """Counts for the Redirects panel.

    Permanent/temporary/flag counts cover every redirect observed, including on
    external links — that is informational. `collapsible_rules` counts only the
    rules you could actually deploy on your own site.
    """
    permanent = temporary = 0
    flagged: dict = {FLAG_LONG_CHAIN: 0, FLAG_HTTP_TO_HTTPS: 0,
                     FLAG_SLASH_BOUNCE: 0, FLAG_LOOP: 0}
    for result in results or []:
        chain = _get(result, "redirect_chain") or []
        kind = classify_redirect(chain)
        if kind == "permanent":
            permanent += 1
        elif kind == "temporary":
            temporary += 1
        for flag in _get(result, "redirect_flags") or []:
            if flag in flagged:
                flagged[flag] += 1
    return {
        "permanent": permanent,
        "temporary": temporary,
        "total": permanent + temporary,
        "flags": flagged,
        "collapsible_rules": len(collapse_rules(results, site_url)),
    }
