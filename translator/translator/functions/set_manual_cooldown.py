from ..common.ratelimit import _LOCK, _MANUAL_COOLDOWN_MAX_HOURS, _MANUAL_COOLDOWN_MIN_HOURS
from ._load_state import _load_state
from ._maybe_reroll_caps import _maybe_reroll_caps
from ._now import _now
from ._prune_log import _prune_log
from ._save_state import _save_state


def set_manual_cooldown(hours):
    """
    Manually forces a hard cooldown -- every reserve() call raises
    RateLimitExceededError until it lifts, independent of the
    hourly/daily caps. Clamped to [1, 72] hours no matter what's passed
    in.

    Only ever extends an already-active cooldown -- never shortens or
    clears one. If the requested cooldown would end sooner than one
    already in effect, the existing (later) end time is kept as-is.
    Returns the epoch timestamp the cooldown lifts at (whichever is
    later: the existing one, or this new request).
    """
    hours = max(_MANUAL_COOLDOWN_MIN_HOURS, min(_MANUAL_COOLDOWN_MAX_HOURS, hours))
    with _LOCK:
        now = _now()
        data = _load_state()
        _prune_log(data, now)
        _maybe_reroll_caps(data, now)

        requested_until = now + hours * 3600
        existing_until = data.get("manual_cooldown_until")
        if existing_until and existing_until > now and existing_until > requested_until:
            until = existing_until  # already-active cooldown runs later -- leave it alone
        else:
            until = requested_until
            data["manual_cooldown_until"] = until
            _save_state(data)
    return until
