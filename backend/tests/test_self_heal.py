"""
Self-heal auto-PR — the most guarded capability.

It writes to real repositories, so its rails are tested to the letter and none
of these tests touch GitHub or the network. Every required enforcement is here:
flag off, allowlist, path blacklist, diff cap, default-branch refusal, verify-
before-PR, fuzzy-in-body-not-diff, and the absence of any merge code path.
"""
import asyncio
import inspect

import pytest

import self_heal as SH
import self_heal_pr as SHP
from self_heal import (
    allowlist, branch_name, guard_not_default_branch, is_allowed_repo,
    is_blacklisted_path, is_editable_path, is_default_branch,
    mixed_content_fixes, redirect_fixes, self_heal_enabled, split_into_prs,
    verify_fixes, within_diff_cap, fuzzy_suggestions,
)
from self_heal_pr import build_pr_body, run_self_heal


# ─── the flag (default OFF) ──────────────────────────────────────────────────
def test_the_flag_is_off_by_default(monkeypatch):
    monkeypatch.delenv(SH.SELF_HEAL_FLAG, raising=False)
    assert self_heal_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "YES"])
def test_the_flag_is_on_only_for_explicit_truthy(monkeypatch, val):
    monkeypatch.setenv(SH.SELF_HEAL_FLAG, val)
    assert self_heal_enabled() is True


# ─── the exact allowlist ─────────────────────────────────────────────────────
def test_allowlist_is_empty_by_default(monkeypatch):
    monkeypatch.delenv(SH.ALLOWLIST_ENV, raising=False)
    assert allowlist() == frozenset()
    assert is_allowed_repo("apexure/site") is False


def test_only_an_exactly_listed_repo_is_allowed():
    allowed = frozenset({"apexure/site"})
    assert is_allowed_repo("apexure/site", allowed) is True
    # No wildcard, no same-org, no suffix expansion.
    assert is_allowed_repo("apexure/site-staging", allowed) is False
    assert is_allowed_repo("apexure/other", allowed) is False
    assert is_allowed_repo("apexure/*", allowed) is False
    assert is_allowed_repo("evil/site", allowed) is False


# ─── the path blacklist ──────────────────────────────────────────────────────
@pytest.mark.parametrize("path", [
    ".github/workflows/deploy.yml", "src/.github/x.yml",
    ".gitlab-ci.yml", ".circleci/config.yml",
    "Dockerfile", "Makefile", "Jenkinsfile",
    "scripts/build.sh", "deploy.ps1", "app/main.py", "index.js", "server.ts",
    "package.json", "package-lock.json", "requirements.txt", "pyproject.toml",
])
def test_blacklisted_paths_are_untouchable(path):
    assert is_blacklisted_path(path) is True
    assert is_editable_path(path) is False


@pytest.mark.parametrize("path", [
    "index.html", "about/index.html", "content/post.md", "data/links.xml",
    "templates/page.njk", "README.md",
])
def test_text_and_markup_paths_are_editable(path):
    assert is_blacklisted_path(path) is False
    assert is_editable_path(path) is True


def test_a_config_json_is_refused_even_though_json_is_text():
    assert is_editable_path("tsconfig.json") is False
    assert is_editable_path("config/settings.json") is False


# ─── provable fixes only ─────────────────────────────────────────────────────
def _redir(old, new, status):
    return {"url": old, "redirect_chain": [{"url": old, "status": status},
                                           {"url": new, "status": 200}]}


def test_a_permanent_redirect_is_a_fix():
    fixes = redirect_fixes([_redir("https://a.test/old", "https://a.test/new", 301)])
    assert len(fixes) == 1 and fixes[0]["new"] == "https://a.test/new"


def test_a_temporary_redirect_is_never_baked_in():
    """302 is temporary — must not be written into source."""
    assert redirect_fixes([_redir("https://a.test/old", "https://a.test/new", 302)]) == []


def test_a_scheme_only_redirect_is_not_a_link_rewrite():
    """http->https is infrastructure, handled as mixed-content, not a rewrite."""
    assert redirect_fixes([_redir("http://a.test/p", "https://a.test/p", 301)]) == []


def test_mixed_content_is_only_flagged_on_an_https_page():
    results = [{"url": "http://cdn.test/a.js", "resource_type": "script"}]
    assert len(mixed_content_fixes(results, "https://site.test/x")) == 1
    assert mixed_content_fixes(results, "http://site.test/x") == []


# ─── verify before PR ────────────────────────────────────────────────────────
def test_only_a_fix_whose_target_resolves_2xx_survives_verification():
    fixes = [{"type": "redirect", "old": "a", "new": "https://ok.test"},
             {"type": "redirect", "old": "b", "new": "https://bad.test"}]

    async def recheck(url):
        return 200 if "ok" in url else 404

    verified = asyncio.run(verify_fixes(fixes, recheck))
    assert [f["new"] for f in verified] == ["https://ok.test"]


def test_a_target_that_errors_on_recheck_is_dropped():
    async def recheck(url):
        raise RuntimeError("network")
    assert asyncio.run(verify_fixes([{"new": "x", "old": "y"}], recheck)) == []


# ─── the diff cap ────────────────────────────────────────────────────────────
def _edit(lines=1):
    return {"old_string": "x", "new_string": "\n".join(["y"] * lines)}


def test_a_small_edit_set_is_within_the_cap():
    assert within_diff_cap([_edit(1), _edit(1)]) is True


def test_an_oversized_set_is_split_into_capped_prs():
    edits = [_edit(20) for _ in range(6)]      # 6 × ~21 lines = well over 50
    groups = split_into_prs(edits)
    assert len(groups) > 1
    for g in groups:
        assert within_diff_cap(g["edits"]) or g["over_cap"]


def test_a_single_edit_larger_than_the_cap_is_flagged_over_cap():
    groups = split_into_prs([_edit(60)])
    assert len(groups) == 1 and groups[0]["over_cap"] is True


# ─── branch mechanics: never the default branch ──────────────────────────────
def test_the_branch_name_is_namespaced_to_linkspy():
    assert branch_name("scan123").startswith("linkspy/fix-")


def test_pushing_to_the_default_branch_raises():
    with pytest.raises(ValueError, match="default branch"):
        guard_not_default_branch("main", "main")


def test_a_linkspy_branch_is_not_the_default_branch():
    assert is_default_branch("linkspy/fix-x", "main") is False
    guard_not_default_branch("linkspy/fix-x", "main")   # does not raise


# ─── fuzzy 404 suggestions: body only, never a diff ──────────────────────────
def test_fuzzy_suggestions_are_extracted_from_broken_links():
    broken = [{"url": "https://a.test/abezt", "bucket": "broken"}]
    sug = fuzzy_suggestions(broken, closest_fn=lambda u: "https://a.test/about")
    assert sug == [{"broken": "https://a.test/abezt", "suggestion": "https://a.test/about"}]


def test_a_suggestion_appears_in_the_body_marked_and_never_as_a_fix():
    body = build_pr_body(
        [{"type": "redirect", "old": "https://a/old", "new": "https://a/new",
          "proof": {"chain": [{"url": "https://a/old", "status": 301},
                              {"url": "https://a/new", "status": 200}], "status": 301}}],
        suggestions=[{"broken": "https://a/abezt", "suggestion": "https://a/about"}],
        fix_type="redirect", verified_at="2026-07-11T00:00:00Z",
        rollback_branch="linkspy/fix-x")
    assert "SUGGESTION — verify before applying" in body
    assert "https://a/abezt" in body
    # The suggestion is under the suggestions heading, not the applied changes.
    applied, _, suggested = body.partition("### SUGGESTIONS")
    assert "abezt" not in applied           # never in the applied section
    assert "abezt" in suggested


# ─── there is NO merge code path ─────────────────────────────────────────────
def test_no_module_contains_a_merge_call():
    for mod in (SH, SHP):
        src = inspect.getsource(mod)
        assert "merge_pr" not in src and ".merge(" not in src
        assert "def merge" not in src


def test_the_repo_ops_contract_has_no_merge():
    """run_self_heal only ever calls open_pr / find_occurrences / default_branch —
    never a merge. (The word "merge" may appear in a safety comment; a merge
    CALL may not.)"""
    src = inspect.getsource(run_self_heal)
    for call in ("repo_ops.merge", ".merge(", "merge_pr", "merge_pull"):
        assert call not in src, call


# ─── the whole orchestration, with a mock repo ───────────────────────────────
class _RepoOps:
    def __init__(self, occurrences_path="index.html"):
        self.path = occurrences_path
        self.opened = []

    def default_branch(self):
        return "main"

    def find_occurrences(self, url):
        return [{"path": self.path}]

    async def open_pr(self, branch, title, body, edits):
        self.opened.append({"branch": branch, "title": title, "body": body, "edits": edits})
        return {"url": f"https://github.com/apexure/site/pull/{len(self.opened)}"}
    # NOTE: deliberately NO merge method.


def _run(**over):
    base = dict(repo="apexure/site", scan_id="scan1",
                results=[_redir("https://apexure.com/old", "https://apexure.com/new", 301)],
                recheck=_ok_recheck, repo_ops=_RepoOps(),
                now_iso="2026-07-11T00:00:00Z", fix_type="redirect")
    base.update(over)
    return asyncio.run(run_self_heal(**base))


async def _ok_recheck(url):
    return 200


def test_flag_off_refuses_everything(monkeypatch):
    monkeypatch.delenv(SH.SELF_HEAL_FLAG, raising=False)
    result = _run()
    assert result["refused"] == "SELF_HEAL is off" and result["prs"] == []


def test_a_non_allowlisted_repo_is_refused(monkeypatch):
    monkeypatch.setenv(SH.SELF_HEAL_FLAG, "on")
    monkeypatch.setenv(SH.ALLOWLIST_ENV, "apexure/other")
    result = _run(repo="apexure/site")
    assert "not on the self-heal allowlist" in result["refused"]
    assert result["prs"] == []


def test_an_allowlisted_repo_opens_a_pr_from_a_linkspy_branch(monkeypatch):
    monkeypatch.setenv(SH.SELF_HEAL_FLAG, "on")
    monkeypatch.setenv(SH.ALLOWLIST_ENV, "apexure/site")
    ops = _RepoOps()
    result = _run(repo_ops=ops)
    assert result["refused"] is None
    assert len(result["prs"]) == 1
    assert result["prs"][0]["branch"].startswith("linkspy/fix-")
    assert "pull/1" in result["prs"][0]["url"]


def test_a_blacklisted_file_occurrence_yields_no_edit(monkeypatch):
    monkeypatch.setenv(SH.SELF_HEAL_FLAG, "on")
    monkeypatch.setenv(SH.ALLOWLIST_ENV, "apexure/site")
    ops = _RepoOps(occurrences_path=".github/workflows/deploy.yml")
    result = _run(repo_ops=ops)
    # The link lives only in a blacklisted file -> nothing is edited, no PR.
    assert result["prs"] == []
    assert ops.opened == []


def test_an_unverifiable_fix_opens_no_pr(monkeypatch):
    monkeypatch.setenv(SH.SELF_HEAL_FLAG, "on")
    monkeypatch.setenv(SH.ALLOWLIST_ENV, "apexure/site")

    async def bad_recheck(url):
        return 404
    result = _run(recheck=bad_recheck)
    assert result["prs"] == []


# ─── the real GitHub layer has no merge, and defends paths in depth ──────────
def test_the_github_layer_has_no_merge_call():
    import self_heal_github, inspect
    src = inspect.getsource(self_heal_github)
    for call in (".merge(", "merge_pr", "merge_pull", "/merge"):
        assert call not in src, call


def test_the_github_layer_refuses_the_default_branch_in_depth():
    import self_heal_github, inspect
    src = inspect.getsource(self_heal_github.GitHubRepoOps._open_pr_sync)
    assert "refusing to write to the default branch" in src


def test_the_endpoint_status_is_read_only_and_reflects_the_flag(monkeypatch):
    import main, self_heal
    monkeypatch.delenv(self_heal.SELF_HEAL_FLAG, raising=False)
    monkeypatch.delenv(self_heal.ALLOWLIST_ENV, raising=False)
    data = asyncio.run(main.self_heal_status())
    assert data["enabled"] is False and data["allowlist"] == []


def test_the_run_endpoint_refuses_when_the_flag_is_off(monkeypatch):
    import main, self_heal
    monkeypatch.delenv(self_heal.SELF_HEAL_FLAG, raising=False)
    resp = asyncio.run(main.self_heal_run(repo="apexure/site", scan_id="s1",
                                          url="https://apexure.com", fix_type="redirect"))
    assert resp.status_code == 403


def test_the_run_endpoint_refuses_a_non_allowlisted_repo(monkeypatch):
    import main, self_heal
    monkeypatch.setenv(self_heal.SELF_HEAL_FLAG, "on")
    monkeypatch.setenv(self_heal.ALLOWLIST_ENV, "apexure/other")
    resp = asyncio.run(main.self_heal_run(repo="apexure/site", scan_id="s1",
                                          url="https://apexure.com", fix_type="redirect"))
    assert resp.status_code == 403
