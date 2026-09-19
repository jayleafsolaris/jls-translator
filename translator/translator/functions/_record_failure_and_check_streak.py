from ..common.translate import FAILURE_STREAK_THRESHOLD, _STOPPED, _consecutive_failures, _streak_lock


def _record_failure_and_check_streak():
    """Increments the run's failure streak. Returns True if this failure
    just pushed it over FAILURE_STREAK_THRESHOLD (i.e. treat as a real
    outage), False if it's still within normal single-item quirk territory."""
    global _consecutive_failures, _STOPPED
    with _streak_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= FAILURE_STREAK_THRESHOLD and not _STOPPED:
            _STOPPED = True
            return True
        return False
