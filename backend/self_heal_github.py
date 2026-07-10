"""
GitHub write layer for self-heal — the only code that talks to a real repo.

It is reached only after self_heal_pr.run_self_heal has cleared every rail (flag
on, repo allowlisted, fixes verified, files not blacklisted, diff within cap,
branch not default). It creates a branch off the default, commits the edits, and
opens a PR. It has NO merge method — self-heal cannot merge, by construction.

The token is a fine-grained PAT scoped to ONLY the allowlisted repo, with
Contents + Pull requests write. It is read from SELF_HEAL_GITHUB_TOKEN and never
logged.
"""
import base64

import httpx

from self_heal import is_editable_path, is_blacklisted_path


_API = "https://api.github.com"


class GitHubRepoOps:
    """Minimal GitHub REST client for one repo. Constructed with the repo and a
    scoped token; every method is read-or-create, never delete, never merge."""

    def __init__(self, repo: str, token: str):
        self.repo = repo                       # "owner/name"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "linkspy-self-heal",
        }
        self._default_branch = None

    def _client(self):
        return httpx.Client(headers=self._headers, timeout=30)

    def default_branch(self) -> str:
        if self._default_branch is None:
            with self._client() as c:
                r = c.get(f"{_API}/repos/{self.repo}")
                r.raise_for_status()
                self._default_branch = r.json()["default_branch"]
        return self._default_branch

    def find_occurrences(self, url: str) -> list:
        """Files in the repo that contain the URL, via code search. Only
        editable, non-blacklisted paths are returned — the write never sees a
        blacklisted file."""
        query = f'"{url}" repo:{self.repo}'
        with self._client() as c:
            r = c.get(f"{_API}/search/code", params={"q": query, "per_page": 30})
            if r.status_code != 200:
                return []
            items = r.json().get("items", [])
        out = []
        for item in items:
            path = item.get("path", "")
            if is_editable_path(path) and not is_blacklisted_path(path):
                out.append({"path": path})
        return out

    async def open_pr(self, branch: str, title: str, body: str, edits: list) -> dict:
        """Create the branch off default, commit each edit, and open a PR. Async
        signature to match the orchestrator; the REST calls run in a thread."""
        import asyncio
        return await asyncio.to_thread(self._open_pr_sync, branch, title, body, edits)

    def _open_pr_sync(self, branch: str, title: str, body: str, edits: list) -> dict:
        base = self.default_branch()
        with self._client() as c:
            # 1. The base branch's head sha.
            ref = c.get(f"{_API}/repos/{self.repo}/git/ref/heads/{base}")
            ref.raise_for_status()
            base_sha = ref.json()["object"]["sha"]

            # 2. Create linkspy/fix-* off it. NEVER the default branch itself.
            if branch == base:
                raise ValueError("refusing to write to the default branch")
            c.post(f"{_API}/repos/{self.repo}/git/refs",
                   json={"ref": f"refs/heads/{branch}", "sha": base_sha})

            # 3. Apply each edit: read file on the branch, replace, commit.
            for edit in edits:
                path = edit["path"]
                if is_blacklisted_path(path) or not is_editable_path(path):
                    continue   # defence in depth — never touch a blacklisted file
                got = c.get(f"{_API}/repos/{self.repo}/contents/{path}",
                            params={"ref": branch})
                if got.status_code != 200:
                    continue
                meta = got.json()
                content = base64.b64decode(meta["content"]).decode("utf-8", "replace")
                if edit["old_string"] not in content:
                    continue
                new_content = content.replace(edit["old_string"], edit["new_string"])
                c.put(f"{_API}/repos/{self.repo}/contents/{path}", json={
                    "message": f"LinkSpy: fix link in {path}",
                    "content": base64.b64encode(new_content.encode("utf-8")).decode(),
                    "sha": meta["sha"], "branch": branch,
                })

            # 4. Open the PR. There is deliberately no call that merges it.
            pr = c.post(f"{_API}/repos/{self.repo}/pulls", json={
                "title": title, "head": branch, "base": base, "body": body,
            })
            pr.raise_for_status()
            return {"url": pr.json().get("html_url")}
