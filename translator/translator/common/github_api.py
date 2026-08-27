"""
GitHub API helpers for --push/--pull (Git Data API: blobs, trees, commits,
refs) and --token (storing/removing the personal access token those calls
authenticate with).

--push/--pull always sync one local folder -- <cwd>/jls-translator/ --
against the exact same-named path in this tool's OWN repo
(GITHUB_OWNER/GITHUB_REPO, from state.py -- not some separately configured
project repo), on whichever branch config_store.get_release_branch()
currently points to (the same branch --upgrade/--release use).
"""

import base64
import hashlib
import os

import requests

from .state import (
    GITHUB_OWNER, GITHUB_REPO, PACKAGE_DIR, DEFAULTS,
    CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME,
)
from .config_store import load_config_value, save_config_value, current_config_dir

_TOKEN_CONFIG_NAME = "github_token"
_API_ROOT = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"

# Local persistent files/folders that must never be pushed up, and must
# never be treated as "stale" and deleted by --pull's mirror step -- same
# names modes/upgrade.py already protects from a fresh GitHub download,
# for the same reason: they live inside the install tree (next to
# common/state.py) but aren't part of the source, they're this specific
# install's cache/config/token. __pycache__/.pyc/.git are excluded too,
# since they're never part of the repo either.
_PROTECTED_NAMES = {
    DEFAULTS["cache_file"], DEFAULTS["languages_json"], DEFAULTS["progress_file"],
    DEFAULTS["update_temp_file"], DEFAULTS["version_check_file"], DEFAULTS["section_order_cache"],
    CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME, "temp_update", "__pycache__", ".git",
}


def is_sync_excluded(rel_posix_path):
    """True if this path (relative to the install root) must be skipped by
    both --push and --pull -- persistent local state, never repo content."""
    if rel_posix_path.endswith(".pyc"):
        return True
    return any(part in _PROTECTED_NAMES for part in rel_posix_path.split("/"))


def find_remote_package_prefix(tree_entries):
    """
    Scans a full recursive tree for wherever cli.py actually lives in the
    repo, and returns that directory as the path prefix everything else
    should be synced under ("" if cli.py sits at the repo root). Returns
    None if cli.py isn't found at all (unexpected repo layout).
    """
    for e in tree_entries:
        if e["type"] == "blob" and e["path"].rsplit("/", 1)[-1] == "cli.py":
            path = e["path"]
            return path.rsplit("/", 1)[0] if "/" in path else ""
    return None



class GitHubAuthError(Exception):
    """Raised whenever the API responds 401/403/404 -- treated uniformly as 'not authorized'."""
    pass


class GitHubApiError(Exception):
    """Any other API failure (network, 5xx, unexpected response shape, truncated tree, etc)."""
    pass


# ---------------------------------------------------------------------
# Token storage (same config-folder convention as delay/release_branch)
# ---------------------------------------------------------------------

def get_token():
    return load_config_value(_TOKEN_CONFIG_NAME, default=None)


def set_token(token):
    save_config_value(_TOKEN_CONFIG_NAME, token)
    path = current_config_dir() / f"{_TOKEN_CONFIG_NAME}.config"
    try:
        os.chmod(path, 0o600)  # best-effort -- not every filesystem (e.g. iOS/a-Shell) supports this
    except Exception:
        pass


def remove_token():
    path = current_config_dir() / f"{_TOKEN_CONFIG_NAME}.config"
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------
# Low-level API plumbing
# ---------------------------------------------------------------------

def _headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = get_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(method, url, **kwargs):
    try:
        resp = requests.request(method, url, headers=_headers(), timeout=15, **kwargs)
    except requests.RequestException as e:
        raise GitHubApiError(str(e))

    # 404 is included here because GitHub returns 404 (not 403) for a
    # private repo you can't see, to avoid confirming it exists -- from
    # the caller's perspective that's still "not authorized".
    if resp.status_code in (401, 403, 404):
        raise GitHubAuthError()
    if not resp.ok:
        raise GitHubApiError(f"GitHub API returned {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}


def get_branch_commit_and_tree(branch):
    """Returns (commit_sha, tree_sha) for the given branch's current HEAD."""
    ref = _request("GET", f"{_API_ROOT}/git/refs/heads/{branch}")
    commit_sha = ref["object"]["sha"]
    commit = _request("GET", f"{_API_ROOT}/git/commits/{commit_sha}")
    return commit_sha, commit["tree"]["sha"]


def get_full_tree(tree_sha):
    """Returns the full recursive tree: a list of {path, mode, type, sha, ...} dicts."""
    data = _request("GET", f"{_API_ROOT}/git/trees/{tree_sha}", params={"recursive": "1"})
    if data.get("truncated"):
        raise GitHubApiError("Repo tree is too large for a single recursive fetch (GitHub truncated it).")
    return data.get("tree", [])


def get_blob_content(sha):
    """Returns the raw bytes of a blob."""
    data = _request("GET", f"{_API_ROOT}/git/blobs/{sha}")
    return base64.b64decode(data["content"])


def create_blob(content_bytes):
    data = _request("POST", f"{_API_ROOT}/git/blobs", json={
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "encoding": "base64",
    })
    return data["sha"]


def create_tree(base_tree_sha, entries):
    """entries: list of {"path", "mode", "type", "sha"} dicts. A "sha" of None
    deletes that path from the resulting tree (relative to base_tree)."""
    data = _request("POST", f"{_API_ROOT}/git/trees", json={
        "base_tree": base_tree_sha,
        "tree": entries,
    })
    return data["sha"]


def create_commit(message, tree_sha, parent_sha):
    data = _request("POST", f"{_API_ROOT}/git/commits", json={
        "message": message,
        "tree": tree_sha,
        "parents": [parent_sha],
    })
    return data["sha"]


def update_ref(branch, commit_sha):
    _request("PATCH", f"{_API_ROOT}/git/refs/heads/{branch}", json={"sha": commit_sha})


def git_blob_sha(content_bytes):
    """
    Computes the same SHA-1 git itself would assign this content as a blob
    object. Lets local files be compared against a remote tree entry's
    `sha` directly, without ever downloading that entry's content just to
    check whether it changed.
    """
    header = f"blob {len(content_bytes)}\0".encode("utf-8")
    return hashlib.sha1(header + content_bytes).hexdigest()
