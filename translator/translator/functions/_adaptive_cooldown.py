from ..common.ratelimit import _MAX_COOLDOWN_MULTIPLIER, _job_remaining_bytes


def _adaptive_cooldown(hour_used, day_used, hour_cap, day_cap, base_delay):
    if _job_remaining_bytes <= 0:
        return base_delay

    hour_remaining_budget = max(1.0, hour_cap - hour_used)
    day_remaining_budget = max(1.0, day_cap - day_used)

    best_multiplier = 1.0
    for remaining_budget in (hour_remaining_budget, day_remaining_budget):
        if _job_remaining_bytes <= remaining_budget:
            continue
        best_multiplier = max(best_multiplier, _job_remaining_bytes / remaining_budget)

    return base_delay * min(best_multiplier, _MAX_COOLDOWN_MULTIPLIER)
