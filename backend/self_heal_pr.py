"""
Self-heal PR assembly and orchestration.

The PR body is an audit trail: every applied change states its finding and its
proof, carries a verification timestamp and a rollback note, and lists the exact
PAT scopes the tool needs. 404 fuzzy matches appear here as SUGGESTIONS only —
never in the diff.

run_self_heal is the orchestrator. All GitHub I/O and the target re-check are
injected, so the whole flow — including "refuse a non-allowlisted repo", "never
touch a blacklisted file", "split an over-cap diff", "never the default branch",
"never merge" — is tested with mocks and no token.
"""
from self_heal import (
    self_heal_enabled, is_allowed_repo, is_blacklisted_path, is_editable_path,
    verify_fixes, within_diff_cap, split_into_prs, branch_name,
    guard_not_default_branch, MAX_DIFF_LINES,
)


PAT_SCOPES_NOTE = (
    "This PR was opened by a GitHub fine-grained personal access token scoped to "
    "ONLY this repository, with **Contents: Read and write** and **Pull requests: "
    "Read and write** and nothing else. The token is never committed and never "
    "logged."
)


def _fix_line(fix) -> str:
    if fix["type"] == "redirect":
        chain = fix["proof"]["chain"]
        hops = " → ".join(f"{c.get('url')} ({c.get('status')})" for c in chain)
        return (f"- **Broken/redirecting link** `{fix['old']}`\n"
                f"  - Proof: {fix['proof']['status']} permanent redirect — {hops}\n"
                f"  - Fix: point it at `{fix['new']}` (its verified destination)\n"
                f"  - Verified 2xx at {fix.get('verified_at', 'n/a')}")
    if fix["type"] == "mixed_content":
        return (f"- **Mixed content** `{fix['old']}` on an HTTPS page\n"
                f"  - Proof: the HTTPS version resolves\n"
                f"  - Fix: `{fix['new']}`\n"
                f"  - Verified 2xx at {fix.get('verified_at', 'n/a')}")
    return f"- {fix.get('old')} → {fix.get('new')}"


def build_pr_body(fixes, suggestions=None, *, fix_type: str, verified_at: str,
                  rollback_branch: str) -> str:
    """The auditable PR description. Applied fixes with proof; suggestions apart
    and clearly not applied."""
    lines = [
        f"## LinkSpy self-heal — {fix_type} fixes",
        "",
        "Each change below is a fix LinkSpy could **prove** from a scan. Nothing "
        "here was inferred or guessed.",
        "",
        "### Applied changes",
    ]
    lines += [_fix_line({**f, "verified_at": verified_at}) for f in fixes]
    lines += [
        "",
        f"**Verification:** every new target was re-checked and returned 2xx at "
        f"{verified_at}, immediately before this PR was opened.",
        "",
        "### Rollback",
        f"Close this PR without merging, or after merging revert it — every "
        f"change is on `{rollback_branch}` and touches only text/markup link "
        f"content. No build, CI, or executable file was modified.",
    ]
    if suggestions:
        lines += [
            "",
            "### SUGGESTIONS — verify before applying (NOT part of this diff)",
            "These are closest-match guesses for broken links. They are **not "
            "applied** and must be checked by a human:",
        ]
        lines += [f"- `{s['broken']}` → maybe `{s['suggestion']}`? "
                  f"**SUGGESTION — verify before applying**" for s in suggestions]
    lines += ["", "---", PAT_SCOPES_NOTE]
    return "\n".join(lines)


def _edits_for(fixes, repo_ops) -> list:
    """Turn verified fixes into concrete file edits, using injected repo search.
    Skips any occurrence in a blacklisted / non-editable file."""
    edits = []
    for fix in fixes:
        for occ in repo_ops.find_occurrences(fix["old"]):
            path = occ.get("path", "")
            if not is_editable_path(path) or is_blacklisted_path(path):
                continue
            edits.append({
                "path": path,
                "old_string": fix["old"],
                "new_string": fix["new"],
                "fix": fix,
            })
    return edits


async def run_self_heal(*, repo: str, scan_id: str, results, recheck, repo_ops,
                        now_iso: str, fix_type: str = "redirect",
                        suggestions=None) -> dict:
    """Open at most a few small PRs of PROVABLE fixes on an allowlisted repo.

    Injected I/O:
      recheck(url)                      -> status/bucket (verify-before-PR)
      repo_ops.default_branch()         -> str
      repo_ops.find_occurrences(url)    -> [{path, ...}]
      repo_ops.open_pr(branch, title, body, edits) -> {url}
    The repo_ops contract has no merge operation, by design — self-heal opens a
    PR and a human merges it.

    Returns a report. Refuses (opens nothing) on any failed rail.
    """
    from self_heal import redirect_fixes, mixed_content_fixes

    # Rail 1: the flag.
    if not self_heal_enabled():
        return {"refused": "SELF_HEAL is off", "prs": []}
    # Rail 2: the exact allowlist.
    if not is_allowed_repo(repo):
        return {"refused": f"{repo} is not on the self-heal allowlist", "prs": []}

    # Rail 3: provable fixes only, one fix-type per PR set.
    if fix_type == "redirect":
        candidate = redirect_fixes(results)
    elif fix_type == "mixed_content":
        candidate = mixed_content_fixes(results)
    else:
        return {"refused": f"unknown fix type {fix_type}", "prs": []}

    # Rail 4: verify every new target 2xx, right now.
    verified = await verify_fixes(candidate, recheck)
    verified = [{**f, "verified_at": now_iso} for f in verified]
    if not verified:
        return {"refused": None, "prs": [], "note": "nothing verifiable to fix"}

    # Rails 5 (blacklist) + 6 (diff cap): concrete edits, split into small PRs.
    edits = _edits_for(verified, repo_ops)
    if not edits:
        return {"refused": None, "prs": [], "note": "no editable file contained the links"}
    groups = [g for g in split_into_prs(edits) if not g["over_cap"]]

    default_branch = repo_ops.default_branch()
    opened = []
    for i, group in enumerate(groups):
        branch = branch_name(f"{scan_id}-{fix_type}-{i+1}" if len(groups) > 1 else f"{scan_id}-{fix_type}")
        # Rail 7: never the default branch.
        guard_not_default_branch(branch, default_branch)
        assert within_diff_cap(group["edits"])   # rail 6, belt and suspenders
        fixes_in_group = [e["fix"] for e in group["edits"]]
        body = build_pr_body(fixes_in_group, suggestions, fix_type=fix_type,
                             verified_at=now_iso, rollback_branch=branch)
        title = f"LinkSpy: fix {len(group['edits'])} {fix_type} link(s)"
        pr = await repo_ops.open_pr(branch, title, body, group["edits"])
        opened.append({"branch": branch, "url": pr.get("url"),
                       "edits": len(group["edits"])})
        # Rail 8: NEVER merge. There is no merge call here, by design.

    return {"refused": None, "prs": opened, "suggestions": len(suggestions or [])}
