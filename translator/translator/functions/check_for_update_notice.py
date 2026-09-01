from ..common.config_store import warn_red, _RESET, get_release_branch
from ..common.state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
import time
from ..common.netcheck import _BLUE
from ._branch_suffix import _branch_suffix
from ._load_version_check_cache import _load_version_check_cache
from ._parse_version_tuple import _parse_version_tuple
from ._save_version_check_cache import _save_version_check_cache
from .fetch_remote_version import fetch_remote_version


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
