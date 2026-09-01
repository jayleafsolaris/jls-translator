from ..common.translate import _STOPPED, _consecutive_failures, _streak_lock


def reset_outage_state():
    """Clears the declared-outage flag and the consecutive-failure streak.

    _STOPPED otherwise latches True for the rest of the process once
    FAILURE_STREAK_THRESHOLD is crossed -- by design, so a single caller
    mid-run doesn't keep hammering a dead service. A caller that backs
    off on its own (e.g. --update's slow-down/retry handling) and wants
    to give Google a genuinely fresh attempt after waiting needs a way to
    lift that latch first; otherwise every retry would short-circuit
    straight back into TranslationUnavailableError without ever touching
    the network again."""
    global _consecutive_failures, _STOPPED
    with _streak_lock:
        _consecutive_failures = 0
        _STOPPED = False
