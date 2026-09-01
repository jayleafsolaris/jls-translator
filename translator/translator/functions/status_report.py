from ..common.ratelimit import _CACHE_TTL_SECONDS, _DAY_SECONDS, _HOUR_SECONDS, _LOCK, _cache_lock, _cached_report, _cached_report_time
from ._format_secs import _format_secs
from ._load_state import _load_state
from ._maybe_reroll_caps import _maybe_reroll_caps
from ._next_reset_epoch import _next_reset_epoch
from ._now import _now
from ._prune_log import _prune_log
from ._save_state import _save_state
from ._usage_within import _usage_within


def status_report(use_cache=True):
    """
    Snapshot of current usage: hour/day percentage used, when each
    window's usage will next tick down, and whether a manual cooldown
    is active. Cached for _CACHE_TTL_SECONDS so a live progress display
    can call this every tick without hitting disk every tick -- pass
    use_cache=False for a guaranteed-fresh read (--usage, end-of-run
    summaries).
    """
    global _cached_report, _cached_report_time

    now = _now()
    if use_cache:
        with _cache_lock:
            if _cached_report is not None and (now - _cached_report_time) < _CACHE_TTL_SECONDS:
                return _cached_report

    with _LOCK:
        data = _load_state()
        _prune_log(data, now)
        _maybe_reroll_caps(data, now)
        _save_state(data)

        day_used = _usage_within(data, now, _DAY_SECONDS)
        hour_used = _usage_within(data, now, _HOUR_SECONDS)
        hour_cap = data["hour_cap"]
        day_cap = data["day_cap"]
        hour_reset_epoch = _next_reset_epoch(data, now, _HOUR_SECONDS)
        day_reset_epoch = _next_reset_epoch(data, now, _DAY_SECONDS)
        cooldown_until = data.get("manual_cooldown_until")

    hour_pct = 100.0 * hour_used / hour_cap if hour_cap else 0.0
    day_pct = 100.0 * day_used / day_cap if day_cap else 0.0
    cooldown_active = bool(cooldown_until and now < cooldown_until)

    report = {
        "hour_pct": min(100.0, hour_pct),
        "day_pct": min(100.0, day_pct),
        "hour_reset_str": _format_secs(hour_reset_epoch - now),
        "day_reset_str": _format_secs(day_reset_epoch - now),
        "hour_reset_epoch": hour_reset_epoch,
        "day_reset_epoch": day_reset_epoch,
        "cooldown_active": cooldown_active,
        "cooldown_until_epoch": cooldown_until if cooldown_active else None,
        "cooldown_reset_str": _format_secs(cooldown_until - now) if cooldown_active else None,
    }

    with _cache_lock:
        _cached_report = report
        _cached_report_time = now

    return report
