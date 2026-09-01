import json
from ..common.ratelimit import _STATE_FILE
from ._default_state import _default_state
from ._now import _now


def _load_state():
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            required = ("hour_cap", "day_cap", "cap_rolled_hour_at", "cap_rolled_day_at", "usage_log")
            if all(k in data for k in required):
                data.setdefault("manual_cooldown_until", None)
                data.setdefault("hour_window_bad", False)
                data.setdefault("day_window_bad", False)
                return data
        except Exception:
            pass
    return _default_state(_now())
