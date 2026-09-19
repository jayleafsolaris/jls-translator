from ..common.translate import _consecutive_failures, _streak_lock


def _record_success():
    global _consecutive_failures
    with _streak_lock:
        _consecutive_failures = 0
