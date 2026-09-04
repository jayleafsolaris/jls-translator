from ..common.ratelimit import _DAY_SECONDS


def _prune_log(data, now):
    """Drops any logged usage older than the daily window -- nothing
    past 24h matters for either the hourly or daily sum."""
    data["usage_log"] = [[ts, b] for ts, b in data["usage_log"] if now - ts < _DAY_SECONDS]
