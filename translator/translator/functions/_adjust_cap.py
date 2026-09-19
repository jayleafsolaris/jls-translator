import random
from ..common.ratelimit import _GROWTH_FACTOR, _GROWTH_UTILIZATION_THRESHOLD, _JITTER_FRACTION, _SHRINK_FACTOR


def _adjust_cap(current_cap, used_bytes, had_outage, min_cap, max_cap):
    """
    AIMD-style adjustment applied once a window (hour or day) finishes:

    - had_outage=True (record_outage() was called during this window --
      a genuine translation outage, not just hitting our own ceiling):
      shrink hard. Real evidence we sent more than Google tolerated.
    - Otherwise, if usage got pushed to at least
      _GROWTH_UTILIZATION_THRESHOLD of the current cap: grow gently.
      This is the only place job size influences the cap, and it does so
      indirectly and safely -- a bigger job produces more real usage,
      which is what earns more room, rather than trusting an a-priori
      estimate to raise the ceiling before there's any evidence it's
      safe.
    - Otherwise (window wasn't pushed hard either way): leave it alone,
      there's nothing to learn from an underused window.

    A small +/- jitter is applied either way so the result isn't
    perfectly deterministic, then clamped to [min_cap, max_cap].
    """
    if had_outage:
        new_cap = current_cap * _SHRINK_FACTOR
    elif current_cap and (used_bytes / current_cap) >= _GROWTH_UTILIZATION_THRESHOLD:
        new_cap = current_cap * _GROWTH_FACTOR
    else:
        new_cap = current_cap

    jitter = 1 + random.uniform(-_JITTER_FRACTION, _JITTER_FRACTION)
    return max(min_cap, min(max_cap, new_cap * jitter))
