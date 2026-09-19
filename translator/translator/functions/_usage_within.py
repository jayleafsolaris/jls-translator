def _usage_within(data, now, window_seconds):
    return sum(b for ts, b in data["usage_log"] if now - ts < window_seconds)
