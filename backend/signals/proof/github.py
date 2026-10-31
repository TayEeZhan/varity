"""GitHub for the Project station: hard checks and repo files, from a pasted public repo link.

Public repos are read with the server's read-only GITHUB_TOKEN (Replit Secret; 5,000 requests an hour, without it
the API allows only 60 an hour for the whole server). Nothing proves the user owns the repo, so it is "unverified".
shortcut: no GitHub sign-in (dropped by decision); add a GitHub App connect if ownership proof or private repos are needed. Hard checks run before any LLM, so a failed check costs no model call.
"""

from __future__ import annotations

import base64
import ipaddress
import os
import re
import socket
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

API = "https://api.github.com"
TIMEOUT_S = 10
MIN_COMMITS = 5        # work added over time, not one dump (team judgement)
MIN_COMMIT_DAYS = 3
MAX_TREE_PATHS = 3000
MAX_FILE_BYTES = 200_000
REPO_RE = re.compile(r"^(?:https?://github\.com/)?([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
PR_RE = re.compile(r"^https://github\.com/([A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100})/pull/(\d{1,7})/?$")


class GithubError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def server_token() -> str | None:
    """A read-only token for public repos (Replit Secret GITHUB_TOKEN)."""
    return os.environ.get("GITHUB_TOKEN") or None


def parse_repo(text: str) -> str | None:
    """'owner/name' from a GitHub URL or slug, else None."""
    m = REPO_RE.match((text or "").strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


class Github:
    """Thin REST client. `send` is replaceable in tests: send(method, url, headers, params) -> (status, json)."""

    def __init__(self, token: str | None = None, send: Callable | None = None):
        self.token = token
        self.send = send or _send

    def get(self, path: str, **params: Any) -> Any:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        status, body = self.send("GET", API + path, headers, params)
        if status >= 400:
            msg = body.get("message") if isinstance(body, dict) else ""
            raise GithubError(f"GitHub {status} on {path}: {msg}", status)
        return body


def _send(method: str, url: str, headers: dict, params: dict) -> tuple[int, Any]:
    try:
        r = httpx.request(method, url, headers=headers, params=params or None, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise GithubError(f"GitHub unreachable: {type(exc).__name__}") from exc
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


# ---- Hard checks (no LLM)

def _check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "ok": ok, "detail": detail}


def _commit_days(commits: list[dict]) -> int:
    return len({c["commit"]["author"]["date"][:10] for c in commits
                if ((c.get("commit") or {}).get("author") or {}).get("date")})


def push_days(gh: Github, repo: str, login: str | None) -> int | None:
    """Days with a push, from GitHub's own event times (a user cannot backdate these). None: no push events
    in GitHub's 90-day window, so the caller falls back to commit dates."""
    events = gh.get(f"/repos/{repo}/events", per_page=100)
    days = {e["created_at"][:10] for e in events if isinstance(e, dict) and e.get("type") == "PushEvent"
            and e.get("created_at") and (not login or ((e.get("actor") or {}).get("login") or "").lower() == login.lower())}
    return len(days) or None


def hard_checks(gh: Github, repo: str, login: str | None, pr_url: str | None = None,
                demo_url: str | None = None, demo_get: Callable[[str], int] | None = None) -> tuple[list[dict], dict]:
    """([check rows], repo info). Stops early only when the repo cannot be read."""
    try:
        info = gh.get(f"/repos/{repo}")
    except GithubError as exc:
        reason = "not found, or private and not shared with Varity" if exc.status in (403, 404) else str(exc)
        return [_check("repo", False, f"Could not read {repo}: {reason}.")], {}
    owner = info["owner"]["login"]
    rows = [_check("repo", True, f"{info['full_name']} · {'private' if info.get('private') else 'public'}")]
    rows.append(_check("owner", True, f"Owned by @{owner} · unverified owner"))
    if info.get("fork"):
        rows.append(_check("fork", False, "This repo is a fork. Submit a repo with your own work."))
    branch = info.get("default_branch") or "main"
    commits = gh.get(f"/repos/{repo}/commits", sha=branch, per_page=100, **({"author": login} if login else {}))
    pushed = push_days(gh, repo, login)
    days = pushed if pushed is not None else _commit_days(commits)
    source = "days with a push" if pushed is not None else "days by commit date (no pushes in GitHub's last 90 days)"
    enough = len(commits) >= MIN_COMMITS and days >= MIN_COMMIT_DAYS
    rows.append(_check("commits", enough, f"{len(commits)}{'+' if len(commits) == 100 else ''} commits, {days} {source}"
                       + ("" if enough else f" (needs {MIN_COMMITS}+ commits on {MIN_COMMIT_DAYS}+ days)")))
    runs = gh.get(f"/repos/{repo}/actions/runs", branch=branch, per_page=1).get("workflow_runs", [])
    if not runs:
        rows.append(_check("ci", False, "No GitHub Actions run found. Add a workflow that runs your tests."))
    else:
        run = runs[0]
        rows.append(_check("ci", run.get("conclusion") == "success",
                           f"Latest Actions run #{run.get('run_number')}: {run.get('conclusion') or run.get('status')}"))
    if pr_url is not None:
        rows.append(pr_check(gh, pr_url, login))
    if demo_url:
        rows.append(demo_check(demo_url, demo_get))
    return rows, {"fullName": info["full_name"], "branch": branch, "owner": owner, "private": bool(info.get("private")),
                  "url": info["html_url"], "head": commits[0].get("sha") if commits else None}


def pr_check(gh: Github, pr_url: str, login: str | None) -> dict:
    m = PR_RE.match(pr_url or "")
    if not m:
        return _check("pr", False, "Give the pull request link (https://github.com/owner/repo/pull/123).")
    pr = gh.get(f"/repos/{m.group(1)}/pulls/{m.group(2)}")
    author = (pr.get("user") or {}).get("login", "")
    if login and author.lower() != login.lower():
        return _check("pr", False, f"Pull request is by @{author}, not by you.")
    merged = bool(pr.get("merged"))
    return _check("pr", merged, "Pull request merged by a maintainer" if merged
                  else "Pull request is not merged yet. A maintainer's merge is the proof.")


def public_host(url: str) -> bool:
    """https only, and every address of the host is public (no SSRF to the server's own network)."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def _demo_get(url: str) -> int:
    return httpx.get(url, timeout=5, follow_redirects=False).status_code


def demo_check(url: str, get: Callable[[str], int] | None = None) -> dict:
    if not public_host(url):
        return _check("demo", False, "Demo link must be a public https address.")
    try:
        status = (get or _demo_get)(url)
    except httpx.HTTPError as exc:
        return _check("demo", False, f"Demo did not answer ({type(exc).__name__}).")
    return _check("demo", 200 <= status < 400, f"Demo answered {status}")


# ---- Repo files for the jury

def list_paths(gh: Github, repo: str, branch: str) -> list[str]:
    tree = gh.get(f"/repos/{repo}/git/trees/{branch}", recursive=1)
    return [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"
            and (t.get("size") or 0) <= MAX_FILE_BYTES][:MAX_TREE_PATHS]


def read_file(gh: Github, repo: str, path: str, branch: str) -> str:
    doc = gh.get(f"/repos/{repo}/contents/{path}", ref=branch)
    if not isinstance(doc, dict) or doc.get("encoding") != "base64":
        return ""
    return base64.b64decode(doc.get("content", "")).decode("utf-8", "replace")
