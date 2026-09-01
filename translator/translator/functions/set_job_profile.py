from ..common.ratelimit import _LOCK, _job_remaining_bytes, _job_remaining_keys


def set_job_profile(remaining_keys, remaining_bytes):
    """
    Call at the start of a --create/--update run (and again to refresh)
    with a rough estimate of how much translation work is left. Only
    shapes the adaptive cooldown -- never the hard caps.
    """
    global _job_remaining_keys, _job_remaining_bytes
    with _LOCK:
        _job_remaining_keys = max(0, remaining_keys)
        _job_remaining_bytes = max(0, remaining_bytes)
