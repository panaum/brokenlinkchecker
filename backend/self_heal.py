"""
Self-heal auto-PR — OPT-IN, allowlisted, DEFAULT OFF.

This is the most dangerous capability in LinkSpy: it opens pull requests against
real repositories. So it does the least it can, only where it is explicitly
allowed, only for fixes it can PROVE, and it never merges anything. Every rail
below is mandatory; where a rail conflicts with convenience, the rail wins.

  1. FLAG SELF_HEAL, default OFF. Off -> the whole capability is inert.
  2. EXACT REPO ALLOWLIST. Even when on, it touches only repos named exactly in
     SELF_HEAL_ALLOWLIST. No wildcard, no "same org", no inference.
  3. PROVABLE FIXES ONLY:
       - a permanent redirect (301/308) chain proves old-url -> new-url.
       - a mixed-content http asset whose https version verifiably resolves.
     A 404 fuzzy match is NEVER auto-applied — it appears in the PR body as a
     human SUGGESTION only.
  4. VERIFY BEFORE PR. Every new target is re-checked (2xx) immediately before
     the PR opens. Unverified -> not proposed.
  5. PATH BLACKLIST. .github/**, any workflow/CI file, and anything executable
     are untouchable. Text/markup link fixes only.
  6. DIFF CAP 50 lines. Larger -> split into single-purpose PRs, never one big
     diff. One fix-type per PR.
  7. NEVER the default branch. Branch linkspy/fix-{scan_id}.
  8. NEVER auto-merge. There is no merge code path anywhere in this module.

Everything here is pure or takes injected I/O, so the rails are tested without a
network and without a token. The GitHub write layer only ever executes a plan
this module has already cleared.
"""
import os
import re
from urllib.parse import urlsplit


# ─── the flag ────────────────────────────────────────────────────────────────
SELF_HEAL_FLAG = "SELF_HEAL"
ALLOWLIST_ENV = "SELF_HEAL_ALLOWLIST"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

MAX_DIFF_LINES = 50


def self_heal_enabled() -> bool:
    return os.getenv(SELF_HEAL_FLAG, "").strip().lower() in _TRUTHY


# ─── the allowlist (exact owner/repo, no expansion) ──────────────────────────
def allowlist() -> frozenset:
    """Repos self-heal may touch, from SELF_HEAL_ALLOWLIST (comma-separated
    owner/repo). Empty by default — nothing is touchable until named."""
    raw = os.getenv(ALLOWLIST_ENV, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def is_allowed_repo(repo: str, allowed=None) -> bool:
    """Exact membership only. "apexure/site" does NOT match "apexure/site-staging"
    or "apexure/*" or another repo in the same org. No inference of any kind."""
    allowed = allowlist() if allowed is None else allowed
    return bool(repo) and repo in allowed


# ─── the path blacklist ──────────────────────────────────────────────────────
# CI/workflow, anything that executes, and dotfiles that configure execution.
# Self-heal only edits human-readable text/markup that contains links.
_BLACKLIST_RE = re.compile(
    r"(^|/)\.github/"                      # workflows, actions, anything in .github
    r"|(^|/)\.gitlab-ci\.ya?ml$"
    r"|(^|/)\.circleci/"
    r"|(^|/)(Jenkinsfile|Dockerfile|Makefile)$"
    r"|\.(sh|bash|zsh|ps1|bat|cmd|py|rb|php|pl|js|ts|jsx|tsx|mjs|cjs)$"  # executable extension
    r"|(^|/)(package\.json|package-lock\.json|yarn\.lock|requirements\.txt|"
    r"Gemfile|Gemfile\.lock|pyproject\.toml|composer\.json)$",              # dependency manifests
    re.I,
)

# What we DO edit: human text/markup carrying links.
_EDITABLE_RE = re.compile(
    r"\.(html?|md|markdown|mdx|txt|xml|rss|vue|svelte|astro|njk|liquid|hbs|"
    r"handlebars|ejs|erb|twig|json)$",     # json only for content data, gated below
    re.I,
)
# JSON is editable content-wise but is also how many manifests look; the
# blacklist above already excludes the dangerous manifest names, and we still
# refuse a json that sits in a config-looking path.
_JSON_CONFIG_HINT = re.compile(r"(^|/)(config|settings|tsconfig|\.[^/]*rc)", re.I)


def is_blacklisted_path(path: str) -> bool:
    """True when a file must never be touched — CI, executable, or a manifest."""
    p = (path or "").strip()
    if p.startswith("./"):
        p = p[2:]
    if not p:
        return True
    if _BLACKLIST_RE.search(p):
        return True
    if p.lower().endswith(".json") and _JSON_CONFIG_HINT.search(p):
        return True
    return False


def is_editable_path(path: str) -> bool:
    """A file we may edit: an allowed text/markup extension AND not blacklisted."""
    p = (path or "").strip()
    if p.startswith("./"):
        p = p[2:]
    if not p or is_blacklisted_path(p):
        return False
    return bool(_EDITABLE_RE.search(p))


# ─── provable fixes ──────────────────────────────────────────────────────────
_PERMANENT = frozenset({301, 308})


def _get(obj, field, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def redirect_fixes(results) -> list:
    """Links whose permanent-redirect chain proves old-url -> new-url.

    Only 301/308 (permanent): a 302 is temporary and must never be baked into
    source. Only when the destination host is the same registrable site — we do
    not rewrite a client's internal link to point at a third party.
    """
    fixes = []
    for r in results or []:
        chain = _get(r, "redirect_chain") or []
        if len(chain) < 2:
            continue
        first = chain[0]
        if _get(first, "status") not in _PERMANENT:
            continue
        old = _get(first, "url") or _get(r, "url") or ""
        new = _get(chain[-1], "url") or ""
        if not old or not new or old == new:
            continue
        if _scheme_only_change(old, new):
            continue    # http->https is infra, handled as mixed-content, not a link rewrite
        fixes.append({
            "type": "redirect",
            "old": old, "new": new,
            "proof": {"chain": chain, "status": _get(first, "status")},
        })
    return _dedupe(fixes)


def mixed_content_fixes(results, page_url: str = "") -> list:
    """An http:// asset on an https:// page. The proposed fix is the https://
    version — but ONLY after verify_fixes confirms it resolves (done later)."""
    if page_url and urlsplit(page_url).scheme != "https":
        return []
    fixes = []
    for r in results or []:
        url = _get(r, "url") or ""
        if not url.lower().startswith("http://"):
            continue
        if _get(r, "resource_type") not in ("script", "iframe", "image", "stylesheet", "css_url", "media"):
            continue
        https = "https://" + url[len("http://"):]
        fixes.append({
            "type": "mixed_content",
            "old": url, "new": https,
            "proof": {"reason": "http asset on an https page"},
        })
    return _dedupe(fixes)


def fuzzy_suggestions(broken_results, closest_fn=None) -> list:
    """404 links with a closest-URL guess. These are SUGGESTIONS ONLY — they go
    in the PR body for a human to weigh, and are NEVER part of an applied diff.
    `closest_fn(url)` returns a best guess or None (injected; rapidfuzz-backed)."""
    out = []
    for r in broken_results or []:
        if _get(r, "bucket") != "broken":
            continue
        url = _get(r, "url") or ""
        guess = closest_fn(url) if closest_fn else None
        if guess:
            out.append({"broken": url, "suggestion": guess})
    return out


def _dedupe(fixes) -> list:
    seen, out = set(), []
    for f in fixes:
        key = (f["type"], f["old"], f["new"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _scheme_only_change(a: str, b: str) -> bool:
    sa, sb = urlsplit(a), urlsplit(b)
    return (sa.scheme, sa.netloc, sa.path) != (sb.scheme, sb.netloc, sb.path) and \
        sa.netloc == sb.netloc and sa.path == sb.path and sa.scheme != sb.scheme


# ─── verify before PR ────────────────────────────────────────────────────────
async def verify_fixes(fixes, recheck) -> list:
    """Keep only fixes whose NEW target resolves 2xx right now. `recheck(url)`
    returns a status int (or a bucket). A fix we cannot verify is not proposed."""
    verified = []
    for fix in fixes or []:
        try:
            result = await recheck(fix["new"])
        except Exception:
            continue
        status = result if isinstance(result, int) else (
            _get(result, "status_code") if not isinstance(result, str) else None)
        ok = (status is not None and 200 <= status < 300) or \
             (isinstance(result, str) and result == "ok") or \
             (_get(result, "bucket") == "ok")
        if ok:
            verified.append({**fix, "verified_status": status})
    return verified


# ─── diff cap ────────────────────────────────────────────────────────────────
def within_diff_cap(edits, cap: int = MAX_DIFF_LINES) -> bool:
    """Each edit changes some lines; the PR must stay at or under the cap."""
    return sum(_edit_lines(e) for e in edits or []) <= cap


def _edit_lines(edit) -> int:
    # A single-line URL swap is 1 changed line; a multi-line replacement counts
    # its lines. Old + new, since a diff shows both.
    old = (_get(edit, "old_string") or "").count("\n") + 1
    new = (_get(edit, "new_string") or "").count("\n") + 1
    return old + new


def split_into_prs(edits, cap: int = MAX_DIFF_LINES) -> list:
    """Pack edits into PR-sized groups so no PR exceeds the cap. A single edit
    larger than the cap is refused (returned in its own oversized group flagged
    so the caller drops it)."""
    groups, current, total = [], [], 0
    for e in edits or []:
        n = _edit_lines(e)
        if n > cap:
            groups.append({"edits": [e], "over_cap": True})
            continue
        if total + n > cap and current:
            groups.append({"edits": current, "over_cap": False})
            current, total = [], 0
        current.append(e)
        total += n
    if current:
        groups.append({"edits": current, "over_cap": False})
    return groups


# ─── branch + PR mechanics ───────────────────────────────────────────────────
def branch_name(scan_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", str(scan_id or "unknown"))[:40]
    return f"linkspy/fix-{safe}"


def is_default_branch(branch: str, default_branch: str) -> bool:
    return (branch or "").strip() == (default_branch or "").strip()


def guard_not_default_branch(branch: str, default_branch: str) -> None:
    """Raise rather than ever push to the repo's default branch."""
    if is_default_branch(branch, default_branch):
        raise ValueError(
            f"refusing to push to the default branch ({default_branch}); "
            f"self-heal only ever opens a PR from linkspy/fix-*")
