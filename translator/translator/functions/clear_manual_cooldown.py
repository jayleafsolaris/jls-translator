from ..common.ratelimit import _LOCK
from ._load_state import _load_state
from ._save_state import _save_state


def clear_manual_cooldown():
    with _LOCK:
        data = _load_state()
        data["manual_cooldown_until"] = None
        _save_state(data)
