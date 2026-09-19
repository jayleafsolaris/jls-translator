from ..common.ratelimit import _DAY_SECONDS, _HOUR_SECONDS, _MAX_DAY_CAP, _MAX_HOUR_CAP, _MIN_DAY_CAP, _MIN_HOUR_CAP
from ._adjust_cap import _adjust_cap
from ._usage_within import _usage_within


def _maybe_reroll_caps(data, now):
    if now - data["cap_rolled_hour_at"] >= _HOUR_SECONDS:
        used = _usage_within(data, now, _HOUR_SECONDS)
        data["hour_cap"] = _adjust_cap(
            data["hour_cap"], used, data.get("hour_window_bad", False), _MIN_HOUR_CAP, _MAX_HOUR_CAP
        )
        data["cap_rolled_hour_at"] = now
        data["hour_window_bad"] = False
    if now - data["cap_rolled_day_at"] >= _DAY_SECONDS:
        used = _usage_within(data, now, _DAY_SECONDS)
        data["day_cap"] = _adjust_cap(
            data["day_cap"], used, data.get("day_window_bad", False), _MIN_DAY_CAP, _MAX_DAY_CAP
        )
        data["cap_rolled_day_at"] = now
        data["day_window_bad"] = False
