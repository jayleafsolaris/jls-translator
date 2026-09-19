from ..common import ratelimit


def _adaptive_cooldown(hour_used, day_used, hour_cap, day_cap, base_delay):
    # Read straight off the ratelimit module's own attribute -- not a
    # value imported at module-load time -- so this actually sees what
    # set_job_profile() most recently wrote. See set_job_profile.py for
    # why importing the name directly doesn't work here.
    remaining_bytes = ratelimit._job_remaining_bytes
    if remaining_bytes <= 0:
        return base_delay

    hour_remaining_budget = max(1.0, hour_cap - hour_used)
    day_remaining_budget = max(1.0, day_cap - day_used)

    best_multiplier = 1.0
    for remaining_budget in (hour_remaining_budget, day_remaining_budget):
        if remaining_bytes <= remaining_budget:
            continue
        best_multiplier = max(best_multiplier, remaining_bytes / remaining_budget)

    return base_delay * min(best_multiplier, ratelimit._MAX_COOLDOWN_MULTIPLIER)
