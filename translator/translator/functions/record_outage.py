from ..common.ratelimit import _LOCK
from ._load_state import _load_state
from ._save_state import _save_state


def record_outage():
    """
    Call when a genuine translation outage is detected (translate.py's
    FAILURE_STREAK_THRESHOLD tripping) -- real evidence Google itself
    pushed back, not just that a run hit our own self-imposed ceiling
    (hitting our own ceiling is expected under real load and isn't
    penalized -- see _adjust_cap()). Marks both windows currently in
    progress so their next reroll shrinks the learned cap instead of
    growing it.
    """
    with _LOCK:
        data = _load_state()
        data["hour_window_bad"] = True
        data["day_window_bad"] = True
        _save_state(data)
