from ..common.config_store import get_request_delay, warn_red
import sys
import threading


def _handle_rate_limit_stop(err):
    """Shared handling for RateLimitExceededError wherever it surfaces:
    print the reason, note that progress is safe to resume from, and end
    the process from the main thread (mirrors how a genuine
    TranslationUnavailableError outage is handled below)."""
    warn_red(str(err))
    print("Progress has been saved -- run --continue once the usage window resets.")
    if threading.current_thread() is threading.main_thread():
        sys.exit(1)
    raise err
