from ..common import ratelimit


def set_job_profile(remaining_keys, remaining_bytes):
    """
    Call at the start of a --create/--update run (and again to refresh)
    with a rough estimate of how much translation work is left. Only
    shapes the adaptive cooldown -- never the hard caps.

    Writes onto the `ratelimit` module's own attributes (not a local
    name) so `_adaptive_cooldown()` -- which reads them the same way --
    actually sees the update. A plain `from ..common.ratelimit import
    _job_remaining_bytes` + `global` here would only rebind a name in
    THIS file's namespace, never touching ratelimit.py's real variable.
    """
    with ratelimit._LOCK:
        ratelimit._job_remaining_keys = max(0, remaining_keys)
        ratelimit._job_remaining_bytes = max(0, remaining_bytes)
