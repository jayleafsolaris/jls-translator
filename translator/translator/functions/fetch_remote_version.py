from ..common.config_store import warn_red, _RESET, get_release_branch
from ..common.state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
import re
import requests
import time


def fetch_remote_version(timeout=4.0, bypass_cache=False):
    """
    Reads just the `version = "..."` line out of pyproject.toml on
    whichever GitHub branch is currently selected as the release branch
    (see config_store.get_release_branch() -- defaults to GITHUB_BRANCH,
    overridable via --release <branch>), without downloading the whole
    repo (that's what --upgrade is for). Returns None on any failure --
    offline, rate-limited, the file moved, a bad connection -- so callers
    can silently skip the update notice instead of erroring out over
    something this minor.

    bypass_cache=True adds a cache-busting query parameter and no-cache
    headers to the request. raw.githubusercontent.com is served through
    Fastly's CDN, which caches responses for a few minutes on its own --
    without this, two checks close together (passive then manual, or two
    manual --check runs) can both hit that same cached response and come
    back identical, which looks exactly like "the check is respecting a
    cooldown" even though this function itself never consults
    DEFAULTS['version_check_interval_minutes'] or any last-checked time
    at all. Used by cmd_check_update() (a bare --check) and by
    check_for_update_notice() whenever force=True (--version), since both
    are explicitly supposed to always be live.
    """
    branch = get_release_branch()
    url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{branch}/pyproject.toml"
    headers = {}
    if bypass_cache:
        url += f"?_={int(time.time() * 1000)}"
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
    try:
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', resp.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None
