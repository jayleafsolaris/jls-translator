from ..common.config_store import warn_red, _RESET, get_release_branch
from ..common.progress import format_duration
from ..common.state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
import time
from ..common.netcheck import _BLUE
from ._branch_suffix import _branch_suffix
from ._load_version_check_cache import _load_version_check_cache
from ._parse_version_tuple import _parse_version_tuple
from ._save_version_check_cache import _save_version_check_cache
from .fetch_remote_version import fetch_remote_version


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
