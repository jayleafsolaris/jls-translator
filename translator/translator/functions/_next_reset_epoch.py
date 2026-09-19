def _next_reset_epoch(data, now, window_seconds):
    """
    Anchored to the most recent logged usage, not the oldest -- every new
    request pushes this further out, so the reset countdown (both what's
    shown to the user and what reserve() actually sleeps for on an hourly
    cap hit) always reflects how recently the tool was actually used,
    instead of draining back down mid-run just because the very first
    request of the window happens to be old.
    """
    in_window = [ts for ts, b in data["usage_log"] if now - ts < window_seconds]
    if not in_window:
        return now
    return max(in_window) + window_seconds
