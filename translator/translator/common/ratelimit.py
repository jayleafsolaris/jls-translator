"""
Network usage rate limiting for translation requests.

Tracks bytes sent to (and received from) Google Translate in rolling
hourly and daily windows, enforcing hard caps that are intentionally NOT
user-configurable -- there is no --config flag anywhere that reads or
writes the ranges below, by design.

The caps are randomized within a fixed range on each window rollover
(a fresh hourly cap is rolled every time the hourly window resets, same
for daily), so the exact ceiling isn't identical run to run -- only the
*range* is fixed, never the number itself, and neither range is exposed
to config_cmd.py or cli.py.

A per-run "job profile" (roughly how many bytes --create/--update still
expects to send, and how many keys that represents) lets the cooldown
between individual requests adapt automatically:

- If the remaining work is on track to fit inside whatever's left of the
  current hourly/daily budget, the cooldown stays at the normal
  configured request delay.
- If it's on track to blow past that budget, the cooldown stretches out
  proportionally, so a big run naturally slows itself down instead of
  burning through the whole allowance in the first few minutes and then
  hard-stopping.

If a request would blow the *daily* cap outright, this raises
RateLimitExceededError rather than sleeping for however many hours are
left -- callers should treat that exactly like a translation outage
(save progress, stop, let --continue pick it back up once the window
resets). Hitting the *hourly* cap just pauses until the next hourly
window opens, since that wait is short enough to sit through.
"""

import json
import random
import threading
import time

from .state import PACKAGE_DIR
from .config_store import get_request_delay, warn_red

# --- Hard caps -------------------------------------------------------
# Deliberately hardcoded here and nowhere else -- no --config flag
# exposes these, and nothing else in the package reads or writes them.
# Units are bytes, KB treated as 1000 bytes (not 1024) for simplicity.
_HOURLY_CAP_RANGE = (100_000, 150_000)   # 100-150 KB per rolling hour
_DAILY_CAP_RANGE = (450_000, 500_000)    # 450-500 KB per rolling day

_HOUR_SECONDS = 60 * 60
_DAY_SECONDS = 24 * 60 * 60

# The adaptive cooldown never stretches past this multiple of the base
# request delay, however far over budget the projected job looks -- past
# this point the hard-cap checks (which pause out the hour, or stop the
# run entirely for a day-cap breach) take over instead of an ever-growing
# per-request sleep.
_MAX_COOLDOWN_MULTIPLIER = 20

_STATE_FILE = PACKAGE_DIR / ".ratelimit_state.json"
_LOCK = threading.Lock()

# Per-process estimate of what the current --create/--update run still
# needs to send. Not persisted -- (re)supplied by cmd_create/cmd_update
# via set_job_profile() at the start of each run. Only ever shapes the
# adaptive cooldown; never affects the hard caps themselves.
_job_remaining_keys = 0
_job_remaining_bytes = 0

# Cheap cache for status_report() so a live progress display can poll it
# every tick without hitting disk every tick.
_cache_lock = threading.Lock()
_cached_report = None
_cached_report_time = 0.0
_CACHE_TTL_SECONDS = 1.0


class RateLimitExceededError(RuntimeError):
    """Raised when the daily usage cap has genuinely been exhausted and
    waiting it out isn't reasonable. Callers should treat this like a
    translation outage: save progress and stop, so --continue can resume
    once the daily window resets."""
    pass


def _now():
    return time.time()


def _default_state(now):
    return {
        "hour_start": now,
        "hour_cap": random.uniform(*_HOURLY_CAP_RANGE),
        "hour_used": 0.0,
        "day_start": now,
        "day_cap": random.uniform(*_DAILY_CAP_RANGE),
        "day_used": 0.0,
    }


def _load_state():
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            required = ("hour_start", "hour_cap", "hour_used", "day_start", "day_cap", "day_used")
            if all(k in data for k in required):
                return data
        except Exception:
            pass
    return _default_state(_now())


def _save_state(data):
    try:
        _STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _roll_windows(data, now):
    """Resets whichever window(s) have expired, re-rolling a fresh random
    cap for that window so the ceiling isn't the same number every time."""
    if now - data["hour_start"] >= _HOUR_SECONDS:
        data["hour_start"] = now
        data["hour_cap"] = random.uniform(*_HOURLY_CAP_RANGE)
        data["hour_used"] = 0.0
    if now - data["day_start"] >= _DAY_SECONDS:
        data["day_start"] = now
        data["day_cap"] = random.uniform(*_DAILY_CAP_RANGE)
        data["day_used"] = 0.0
    return data


def _format_secs(secs):
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def set_job_profile(remaining_keys, remaining_bytes):
    """
    Call once at the start of a --create/--update run (and again anytime
    the caller wants to refresh the estimate) with a rough estimate of
    how much translation work is left: remaining_keys is a plain count,
    remaining_bytes is the total UTF-8 size of the text still to be sent.

    This only shapes the adaptive cooldown between requests -- it never
    affects the hard hourly/daily caps.
    """
    global _job_remaining_keys, _job_remaining_bytes
    with _LOCK:
        _job_remaining_keys = max(0, remaining_keys)
        _job_remaining_bytes = max(0, remaining_bytes)


def _adaptive_cooldown(data, now, base_delay):
    """
    How long to wait before the *next* request, given how the current
    job's remaining estimated bytes compare to what's left in the hourly
    and daily budgets. Only ever stretches the delay out -- never
    shortens it below base_delay.
    """
    if _job_remaining_bytes <= 0:
        return base_delay

    hour_remaining_budget = max(1.0, data["hour_cap"] - data["hour_used"])
    day_remaining_budget = max(1.0, data["day_cap"] - data["day_used"])

    best_multiplier = 1.0
    for remaining_budget in (hour_remaining_budget, day_remaining_budget):
        if _job_remaining_bytes <= remaining_budget:
            continue  # this window's budget comfortably covers the rest of the job
        overrun_ratio = _job_remaining_bytes / remaining_budget
        best_multiplier = max(best_multiplier, overrun_ratio)

    best_multiplier = min(best_multiplier, _MAX_COOLDOWN_MULTIPLIER)
    return base_delay * best_multiplier


def reserve(num_bytes):
    """
    Call this right before actually sending a request to Google Translate,
    with the UTF-8 byte size of the outgoing text.

    - Applies the adaptive cooldown (sleeps) before letting the request
      through, if the current job looks likely to outrun its remaining
      budget.
    - If this request would exceed the *hourly* cap, sleeps until the
      next hourly window opens and re-checks (daily budget permitting).
    - If this request would exceed the *daily* cap, raises
      RateLimitExceededError instead of sleeping for hours.

    Thread-safe -- safe to call concurrently from translate_many's worker
    threads.
    """
    base_delay = get_request_delay()

    while True:
        cooldown = None
        wait_secs = None

        with _LOCK:
            now = _now()
            data = _roll_windows(_load_state(), now)

            if data["day_used"] + num_bytes > data["day_cap"]:
                _save_state(data)
                reset_str = _format_secs(_DAY_SECONDS - (now - data["day_start"]))
                raise RateLimitExceededError(
                    f"Daily translation usage limit reached. Resets in {reset_str}."
                )

            if data["hour_used"] + num_bytes > data["hour_cap"]:
                wait_secs = max(1.0, _HOUR_SECONDS - (now - data["hour_start"]) + 1)
                _save_state(data)
            else:
                cooldown = _adaptive_cooldown(data, now, base_delay)
                data["hour_used"] += num_bytes
                data["day_used"] += num_bytes
                _save_state(data)

        if wait_secs is not None:
            # Hourly cap hit but the daily budget still has room -- wait
            # out the rest of this hour rather than stopping the run.
            warn_red(
                f"Hourly translation usage limit reached -- pausing "
                f"{_format_secs(wait_secs)} until the next hourly window."
            )
            time.sleep(min(wait_secs, _HOUR_SECONDS))
            continue

        if cooldown and cooldown > 0:
            time.sleep(cooldown)
        return


def record_extra(num_bytes):
    """
    Adds additional bytes (e.g. the translated response payload, which
    isn't known until after the request completes) to the current usage
    counters after the fact. Never blocks and never raises -- the hard
    caps are only enforced going into reserve(), not on this top-up, so a
    response that came back larger than expected doesn't retroactively
    fail an already-completed request.
    """
    if num_bytes <= 0:
        return
    with _LOCK:
        now = _now()
        data = _roll_windows(_load_state(), now)
        data["hour_used"] += num_bytes
        data["day_used"] += num_bytes
        _save_state(data)


def status_report(use_cache=True):
    """
    Snapshot of current usage for display: hour/day percentage used and
    time until each window resets. Cached for _CACHE_TTL_SECONDS so a
    live progress display can call this every tick without hitting disk
    every tick -- pass use_cache=False for a guaranteed-fresh read (e.g.
    the final summary at the end of a run).
    """
    global _cached_report, _cached_report_time

    now = _now()
    if use_cache:
        with _cache_lock:
            if _cached_report is not None and (now - _cached_report_time) < _CACHE_TTL_SECONDS:
                return _cached_report

    with _LOCK:
        data = _roll_windows(_load_state(), now)
        _save_state(data)

    hour_pct = 100.0 * data["hour_used"] / data["hour_cap"] if data["hour_cap"] else 0.0
    day_pct = 100.0 * data["day_used"] / data["day_cap"] if data["day_cap"] else 0.0

    hour_reset_epoch = data["hour_start"] + _HOUR_SECONDS
    day_reset_epoch = data["day_start"] + _DAY_SECONDS

    report = {
        "hour_pct": min(100.0, hour_pct),
        "day_pct": min(100.0, day_pct),
        "hour_reset_str": _format_secs(hour_reset_epoch - now),
        "day_reset_str": _format_secs(day_reset_epoch - now),
        # Absolute epoch timestamps for callers (e.g. --usage) that want
        # to show a clock time rather than just a relative countdown.
        "hour_reset_epoch": hour_reset_epoch,
        "day_reset_epoch": day_reset_epoch,
    }

    with _cache_lock:
        _cached_report = report
        _cached_report_time = now

    return report