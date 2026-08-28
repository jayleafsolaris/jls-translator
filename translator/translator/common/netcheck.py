"""
Internet connectivity probing and the passive/manual GitHub version-check
used for the update notice, --check, and --upgrade.
"""

import concurrent.futures
import json
import re
import time

import requests

from .state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
from .config_store import warn_red, _RESET, get_release_branch
from .progress import format_duration

def check_internet(timeout=1.2):
    """
    Quick, cheap connectivity probe. Tries a couple of well-known, highly
    available hosts on their DNS port so we don't depend on Google Translate
    itself (or DNS resolution of a hostname) just to find out whether we're
    online at all.

    The hosts are probed concurrently, not one after another -- a slow or
    silently-dropping connection to one host no longer doubles the wait.
    Worst case is roughly `timeout` seconds total (not `timeout` per host).
    Returns True on the first successful TCP connect, False if every
    attempt fails or times out.
    """
    import socket

    hosts = [("8.8.8.8", 53), ("1.1.1.1", 53)]

    def _try(host_port):
        host, port = host_port
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [ex.submit(_try, hp) for hp in hosts]
        for fut in concurrent.futures.as_completed(futures):
            if fut.result():
                return True
    return False


def require_internet_or_warn(flag_name):
    """
    Call at the top of any command that needs network access (translation
    calls to Google Translate). Warns and returns False if offline, so the
    caller can bail out before doing any work or touching progress/cache
    files.

    Uses a short timeout: both probe hosts are tried concurrently, so an
    offline machine (which fails fast with "network unreachable" or
    "connection refused" rather than hanging) is reported back almost
    instantly. The timeout is only a ceiling for the rarer case of a
    connection that silently drops packets instead of refusing them.
    """
    if check_internet(timeout=0.6):
        return True
    warn_red(
        f"No internet connection detected, {flag_name} needs network access "
        f"to function in this state!"
    )
    print(f"{_BLUE}Check your connection and try again!{_RESET}")
    return False


_YELLOW = "\033[93m"
_BLUE = "\033[94m"


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


def _parse_version_tuple(version_string):
    """
    Best-effort parse of a dotted version string into a tuple of ints for
    comparison (e.g. '1.5.10' -> (1, 5, 10)), ignoring any non-numeric
    suffix on a segment (e.g. '2rc1' -> 2) so odd version strings don't
    blow up the comparison.
    """
    parts = []
    for chunk in version_string.split("."):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group(0)) if m else 0)
    return tuple(parts)


def _load_version_check_cache():
    path = PACKAGE_DIR / DEFAULTS["version_check_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_version_check_cache(data):
    path = PACKAGE_DIR / DEFAULTS["version_check_file"]
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _branch_suffix():
    """
    A short " (Current Branch: X)" annotation appended to update-notice
    messages whenever the release branch has been overridden away from
    the repo's normal default (GITHUB_BRANCH) -- so a custom branch's
    version checks are clearly labeled, while the common default-branch
    case stays exactly as quiet/plain as before.
    """
    branch = get_release_branch()
    if branch == GITHUB_BRANCH:
        return ""
    return f" (Current Branch: {branch})"


def check_for_update_notice(force=False):
    """
    Best-effort, silent-on-failure notice printed when a newer version is
    available on GitHub than the one currently installed/running.

    Only reaches out to the network at most once every
    DEFAULTS['version_check_interval_minutes'] minutes (tracked in a small
    cache file next to the package), so this never adds network latency to
    every-day command usage. Pass force=True (used by --version and a bare
    --check) to always check fresh regardless of that interval.

    When a check is due, this makes exactly one short, low-timeout network
    attempt (no separate "are we online" probe beforehand) so an offline
    or slow connection is discovered and given up on quickly instead of
    waiting out two stacked timeouts.

    The passive/automatic check can be turned off entirely with
    `--check false` (see the "autocheck_enabled" flag in the version-check
    cache) -- while off, this function does nothing unless force=True, so
    --version and a bare --check still always work even with autocheck
    disabled.

    Never raises and never blocks a command on a slow/offline connection --
    worst case this simply prints nothing.
    """
    cache = _load_version_check_cache()
    if not force and cache.get("autocheck_enabled", True) is False:
        return
    now = time.time()
    last_checked = cache.get("last_checked", 0)
    interval_seconds = DEFAULTS["version_check_interval_minutes"] * 60

    remote = cache.get("remote_version")
    stale = force or (now - last_checked) > interval_seconds

    if stale:
        # Passive checks stay snappy with a short timeout; a forced check
        # (--version, bare --check) can afford to wait a bit longer for an
        # accurate answer since the user explicitly asked for one, and
        # bypasses raw.githubusercontent.com's CDN cache so it's genuinely
        # live rather than possibly a few-minutes-stale cached response.
        fetched = fetch_remote_version(timeout=1.5 if not force else 3.0, bypass_cache=force)
        if fetched:
            remote = fetched
            cache["remote_version"] = remote
            cache["last_checked"] = now
            _save_version_check_cache(cache)
        else:
            # Offline, blocked, slow, or GitHub unreachable -- stay quiet
            # rather than block the command or report a stale result.
            return

    if not remote:
        return

    try:
        is_newer = _parse_version_tuple(remote) > _parse_version_tuple(SCRIPT_VERSION)
    except Exception:
        return

    if is_newer:
        print(f"{_BLUE}⬆ Update available: v{SCRIPT_VERSION} → v{remote}{_branch_suffix()} "
              f">> run --upgrade to update.{_RESET}")


def cmd_check_update():
    """
    Manually, immediately checks GitHub for a newer version -- always hits
    the network (ignoring DEFAULTS['version_check_interval_minutes']) and
    prints the result either way. This is `--check` used with no value.

    Gated by its own separate cooldown (DEFAULTS['check_cooldown_seconds'],
    3 minutes) tracked as "last_manual_check" in the same version-check
    cache file -- independent of the passive checker's interval/timestamp,
    so this can't be spammed regardless of what raw.githubusercontent.com's
    CDN does on its end. The cooldown starts counting from the moment a
    check is actually attempted (not from a successful result), so a
    string of offline attempts is throttled too.

    Makes exactly one network attempt (fetch_remote_version, with
    bypass_cache=True so raw.githubusercontent.com's CDN can't hand back a
    stale cached response) rather than a separate "are we online" probe
    followed by the real request, so an offline connection is reported
    quickly instead of after two stacked timeouts.

    Purely informational: it does NOT change whether the passive/automatic
    checker keeps running on other commands -- use `--check true` or
    `--check false` for that.
    """
    cache = _load_version_check_cache()
    now = time.time()
    cooldown = DEFAULTS["check_cooldown_seconds"]
    elapsed = now - cache.get("last_manual_check", 0)
    if elapsed < cooldown:
        print(f"You can’t check for updates yet! Try again in {format_duration(cooldown - elapsed)}")
        return

    cache["last_manual_check"] = now
    _save_version_check_cache(cache)

    print(f"Checking for updates{_branch_suffix()}...")

    remote = fetch_remote_version(timeout=3.0, bypass_cache=True)
    now = time.time()

    if not remote:
        warn_red("Couldn't reach GitHub - no internet connection, or GitHub is unreachable.")
        return

    cache["remote_version"] = remote
    cache["last_checked"] = now
    _save_version_check_cache(cache)

    try:
        is_newer = _parse_version_tuple(remote) > _parse_version_tuple(SCRIPT_VERSION)
    except Exception:
        is_newer = None

    if is_newer:
        print(f"{_BLUE}⬆ Update available: v{SCRIPT_VERSION} → v{remote}{_branch_suffix()} "
              f">> run --upgrade to update.{_RESET}")
    elif is_newer is False:
        print(f"Up to date: v{SCRIPT_VERSION} is the latest version.")
    else:
        print(f"Current version: v{SCRIPT_VERSION} (latest on GitHub: v{remote}, couldn't compare).")


def cmd_set_autocheck(enabled):
    """
    Turns the passive/automatic update check (the one that silently runs
    at the top of every command) on or off, via `--check true` / `--check
    false`. Does not itself hit the network or change the cached remote
    version -- it only flips the stored flag that check_for_update_notice()
    consults.
    """
    cache = _load_version_check_cache()
    cache["autocheck_enabled"] = enabled
    _save_version_check_cache(cache)
    if enabled:
        print(f"Automatic update checks are now enabled (checks at most every "
              f"{DEFAULTS['version_check_interval_minutes']} minutes).")
    else:
        print("Automatic update checks are now disabled. Run --check anytime to check manually.")
