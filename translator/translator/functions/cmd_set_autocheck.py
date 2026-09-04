from ..common.state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
from ._load_version_check_cache import _load_version_check_cache
from ._save_version_check_cache import _save_version_check_cache


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
