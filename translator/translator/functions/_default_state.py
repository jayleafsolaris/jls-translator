import random
from ..common.ratelimit import _INITIAL_DAILY_CAP_RANGE, _INITIAL_HOURLY_CAP_RANGE


def _default_state(now):
    return {
        "hour_cap": random.uniform(*_INITIAL_HOURLY_CAP_RANGE),
        "day_cap": random.uniform(*_INITIAL_DAILY_CAP_RANGE),
        "cap_rolled_hour_at": now,
        "cap_rolled_day_at": now,
        "hour_window_bad": False,
        "day_window_bad": False,
        "usage_log": [],
        "manual_cooldown_until": None,
    }
