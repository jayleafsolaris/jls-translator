from ..common.config_store import warn_red, _RESET, get_release_branch
from ..common.netcheck import _BLUE
from .check_internet import check_internet


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
