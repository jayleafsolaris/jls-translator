from ..common.ratelimit import _LOCK
from ._load_state import _load_state
from ._maybe_reroll_caps import _maybe_reroll_caps
from ._now import _now
from ._prune_log import _prune_log
from ._save_state import _save_state


def record_extra(num_bytes):
    """
    Adds additional bytes (e.g. the translated response payload, only
    known after the request completes) to the sliding usage log. Never
    blocks and never raises.
    """
    if num_bytes <= 0:
        return
    with _LOCK:
        now = _now()
        data = _load_state()
        _prune_log(data, now)
        _maybe_reroll_caps(data, now)
        data["usage_log"].append([now, num_bytes])
        _save_state(data)
