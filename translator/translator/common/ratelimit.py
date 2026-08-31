"""
Network usage rate limiting for translation requests.

Tracks bytes sent to (and received from) Google Translate as a SLIDING
window log -- each request is logged as (timestamp, bytes), and "usage
this hour" / "usage today" is always the sum of whatever's still inside
the trailing 60-minute / 24-hour window. This is deliberate: with a fixed
bucket that only resets at a fixed clock boundary, running --update
in the middle of an existing window doesn't move the reset countdown at
all (it just adds to a bucket that resets whenever it resets, regardless
of when the most recent activity happened) -- which reads as "the
countdown is frozen." With a sliding window anchored to the *most
recent* logged request (see _next_reset_epoch()), every new request
pushes the reset countdown further out, so it always reflects how
recently the tool was actually used instead of a timestamp frozen
from whenever the state file was first created.

Hard caps (bytes, KB = 1000 bytes) are LEARNED, not hardcoded -- there's
no documented real quota for the unofficial endpoint deep_translator
hits, so the only trustworthy way to know how much can actually be sent
is to watch what actually happens:

  - GROW the cap when a whole hour/day window finishes with real demand
    (usage got pushed close to the current ceiling) and nothing went
    wrong -- i.e. a bigger job needed more room and Google didn't
    object, so there was headroom to spare. This is what makes the cap
    track actual job sizes automatically, without reading any job
    estimate directly: a bigger job naturally produces more usage,
    which naturally earns more room over time.
  - SHRINK the cap hard when a genuine outage was detected during the
    window (see translate.py's FAILURE_STREAK_THRESHOLD and this
    module's record_outage()) -- real evidence Google itself pushed
    back, as opposed to merely bumping into our own self-imposed
    ceiling (which is expected and not penalized).

See _adjust_cap()/_maybe_reroll_caps() below for the actual mechanics.
The _INITIAL_*_CAP_RANGE constants only seed a brand-new state file
before anything has been learned yet; _MIN_*_CAP/_MAX_*_CAP are sanity
backstops so growth/shrinkage can't run away to a degenerate value, not
ongoing hardcoded limits themselves.

A per-run "job profile" (how many bytes --create/--update still expects
to send) additionally lets the cooldown between individual requests
adapt within a single run: if the remaining work fits inside what's left
of the current budget, the cooldown stays at the normal configured
request delay; if it's on track to blow past that budget, the cooldown
stretches out proportionally.

On top of the automatic caps, --usage --24hr <hours> lets you manually
force a hard cooldown (1-72 hours) that blocks every translation request
until it lifts, independent of the hourly/daily budgets.
"""

import json
import random
import threading
import time

from .state import PACKAGE_DIR
from .config_store import get_request_delay, warn_red
from . import debug_log

# --- Learned caps ------------------------------------------------------
# Only used to seed a brand-new state file -- once a real cap has been
# learned (see module docstring), these ranges are never consulted again.
_INITIAL_HOURLY_CAP_RANGE = (100_000, 1_500_000)   # 100 KB - 1.5 MB seed
_INITIAL_DAILY_CAP_RANGE = (4_500_000, 5_000_000)   # 4.5 MB - 5.0 MB seed

# Sanity floor/ceiling -- growth/shrinkage can never cross these no
# matter how many clean windows or outages happen in a row. Wide enough
# to give the learning process real room to move in either direction.
_MIN_HOUR_CAP = 150_000
_MAX_HOUR_CAP = 1_500_000
_MIN_DAY_CAP = 4_500_000
_MAX_DAY_CAP = 5_000_000

# AIMD tuning: additive-ish growth, multiplicative (hard) backoff -- the
# classic shape for learning a safe ceiling against an unknown, possibly
# adversarial limit, without needing to know the real number in advance.
_GROWTH_FACTOR = 1.15
_SHRINK_FACTOR = 0.5
# Only grow if the window was actually pushed close to its ceiling --
# growing an underused cap teaches the limiter nothing real.
_GROWTH_UTILIZATION_THRESHOLD = 0.6
# Small +/- randomness on every adjustment so the learned cap isn't
# perfectly deterministic run to run (same reasoning the old fixed-range
# reroll had for varying the exact ceiling call to call).
_JITTER_FRACTION = 0.05

_HOUR_SECONDS = 1.5 * 60 * 60
_DAY_SECONDS = 24 * 60 * 60

_MANUAL_COOLDOWN_MIN_HOURS = 1
_MANUAL_COOLDOWN_MAX_HOURS = 72

# The adaptive cooldown never stretches past this multiple of the base
# request delay -- past this point the hard-cap checks (which pause out
# the hour, or stop the run entirely for a day-cap breach) take over.
_MAX_COOLDOWN_MULTIPLIER = 20

_STATE_FILE = PACKAGE_DIR / ".ratelimit_state.json"
_LOCK = threading.Lock()

# Per-process estimate of what the current --create/--update run still
# needs to send. Not persisted -- (re)supplied via set_job_profile() at
# the start of each run. Only shapes the adaptive cooldown, never the
# hard caps.
_job_remaining_keys = 0
_job_remaining_bytes = 0

# Cheap cache for status_report() so a live progress display can poll it
# every tick without hitting disk every tick.
_cache_lock = threading.Lock()
_cached_report = None
_cached_report_time = 0.0
_CACHE_TTL_SECONDS = 1.0


class RateLimitExceededError(RuntimeError):
    """Raised when the daily cap, or a manually-set cooldown, blocks a
    request outright. Callers should treat this like an outage: save
    progress and stop, so --continue can resume once it lifts."""
    pass


def _now():
    return time.time()


def _default_state(now):
    return {
        "hour_cap": random.uniform(*_INITIAL_HOURLY_CAP_RANGE),
        "day_cap": random.uniform(*_INITIAL_DAILY_CAP_RANGE),
        "cap_rolled_hour_at": now,
        "cap_rolled_day_at": now,
        # Set by record_outage() whenever a genuine outage happens during
        # the window currently in progress -- consulted (and cleared) the
        # next time that window's cap rerolls, so a bad window shrinks
        # the cap instead of growing it.
        "hour_window_bad": False,
        "day_window_bad": False,
        "usage_log": [],  # list of [epoch, bytes], pruned to the trailing 24h
        "manual_cooldown_until": None,
    }


def _load_state():
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            required = ("hour_cap", "day_cap", "cap_rolled_hour_at", "cap_rolled_day_at", "usage_log")
            if all(k in data for k in required):
                data.setdefault("manual_cooldown_until", None)
                data.setdefault("hour_window_bad", False)
                data.setdefault("day_window_bad", False)
                return data
        except Exception:
            pass
    return _default_state(_now())


def _save_state(data):
    try:
        _STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _prune_log(data, now):
    """Drops any logged usage older than the daily window -- nothing
    past 24h matters for either the hourly or daily sum."""
    data["usage_log"] = [[ts, b] for ts, b in data["usage_log"] if now - ts < _DAY_SECONDS]


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


def _maybe_reroll_caps(data, now):
    if now - data["cap_rolled_hour_at"] >= _HOUR_SECONDS:
        used = _usage_within(data, now, _HOUR_SECONDS)
        data["hour_cap"] = _adjust_cap(
            data["hour_cap"], used, data.get("hour_window_bad", False), _MIN_HOUR_CAP, _MAX_HOUR_CAP
        )
        data["cap_rolled_hour_at"] = now
        data["hour_window_bad"] = False
    if now - data["cap_rolled_day_at"] >= _DAY_SECONDS:
        used = _usage_within(data, now, _DAY_SECONDS)
        data["day_cap"] = _adjust_cap(
            data["day_cap"], used, data.get("day_window_bad", False), _MIN_DAY_CAP, _MAX_DAY_CAP
        )
        data["cap_rolled_day_at"] = now
        data["day_window_bad"] = False


def record_outage():
    """
    Call when a genuine translation outage is detected (translate.py's
    FAILURE_STREAK_THRESHOLD tripping) -- real evidence Google itself
    pushed back, not just that a run hit our own self-imposed ceiling
    (hitting our own ceiling is expected under real load and isn't
    penalized -- see _adjust_cap()). Marks both windows currently in
    progress so their next reroll shrinks the learned cap instead of
    growing it.
    """
    with _LOCK:
        data = _load_state()
        data["hour_window_bad"] = True
        data["day_window_bad"] = True
        _save_state(data)


def _usage_within(data, now, window_seconds):
    return sum(b for ts, b in data["usage_log"] if now - ts < window_seconds)


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


def _format_secs(secs):
    secs = max(0, int(secs))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)

    units = [("d", d), ("h", h), ("m", m), ("s", s)]
    nonzero = [(label, val) for label, val in units if val]

    if not nonzero:
        return "0s"
    return " ".join(f"{val}{label}" for label, val in nonzero)


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


def set_manual_cooldown(hours):
    """
    Manually forces a hard cooldown -- every reserve() call raises
    RateLimitExceededError until it lifts, independent of the
    hourly/daily caps. Clamped to [1, 72] hours no matter what's passed
    in.

    Only ever extends an already-active cooldown -- never shortens or
    clears one. If the requested cooldown would end sooner than one
    already in effect, the existing (later) end time is kept as-is.
    Returns the epoch timestamp the cooldown lifts at (whichever is
    later: the existing one, or this new request).
    """
    hours = max(_MANUAL_COOLDOWN_MIN_HOURS, min(_MANUAL_COOLDOWN_MAX_HOURS, hours))
    with _LOCK:
        now = _now()
        data = _load_state()
        _prune_log(data, now)
        _maybe_reroll_caps(data, now)

        requested_until = now + hours * 3600
        existing_until = data.get("manual_cooldown_until")
        if existing_until and existing_until > now and existing_until > requested_until:
            until = existing_until  # already-active cooldown runs later -- leave it alone
        else:
            until = requested_until
            data["manual_cooldown_until"] = until
            _save_state(data)
    return until


def clear_manual_cooldown():
    with _LOCK:
        data = _load_state()
        data["manual_cooldown_until"] = None
        _save_state(data)


def reserve(num_bytes):
    """
    Call right before sending a request to Google Translate, with the
    UTF-8 byte size of the outgoing text.

    - Blocks immediately if a manual cooldown (--usage --24hr) is active.
    - Raises RateLimitExceededError if this request would exceed the
      daily cap.
    - Sleeps until the hourly window clears since your most recent
      request if this request would exceed the hourly cap (daily budget
      permitting).
    - Otherwise applies the adaptive cooldown and logs the usage.

    Thread-safe -- safe to call concurrently from translate_many's
    worker threads.
    """
    base_delay = get_request_delay()

    while True:
        cooldown = None
        wait_secs = None

        with _LOCK:
            now = _now()
            data = _load_state()
            _prune_log(data, now)
            _maybe_reroll_caps(data, now)

            cooldown_until = data.get("manual_cooldown_until")
            if cooldown_until and now < cooldown_until:
                _save_state(data)
                raise RateLimitExceededError(
                    f"Manual cooldown active. Resets in {_format_secs(cooldown_until - now)}."
                )

            day_used = _usage_within(data, now, _DAY_SECONDS)
            hour_used = _usage_within(data, now, _HOUR_SECONDS)

            if day_used + num_bytes > data["day_cap"]:
                _save_state(data)
                reset_epoch = _next_reset_epoch(data, now, _DAY_SECONDS)
                raise RateLimitExceededError(
                    f"Daily translation usage limit reached. Resets in {_format_secs(reset_epoch - now)}."
                )

            if hour_used + num_bytes > data["hour_cap"]:
                reset_epoch = _next_reset_epoch(data, now, _HOUR_SECONDS)
                wait_secs = max(1.0, reset_epoch - now)
                _save_state(data)
            else:
                cooldown = _adaptive_cooldown(hour_used, day_used, data["hour_cap"], data["day_cap"], base_delay)
                data["usage_log"].append([now, num_bytes])
                _save_state(data)

        if wait_secs is not None:
            warn_red(
                f"Hourly translation usage limit reached -- pausing "
                f"{_format_secs(wait_secs)} for the hourly window to clear."
            )
            debug_log.log(f"hourly cap hit -- sleeping {wait_secs:.0f}s (not stuck, this is deliberate)")
            time.sleep(min(wait_secs, _HOUR_SECONDS))
            debug_log.log("hourly pause finished -- rechecking")
            continue

        if cooldown and cooldown > 0:
            debug_log.log(f"adaptive cooldown -- sleeping {cooldown:.1f}s")
            time.sleep(cooldown)
        return


def record_extra(num_bytes):
    """
    Adds additional bytes (e.g. the translated response payload, only
    known after the request completes) to the sliding usage log. Never
    blocks and never raises.
    """
    if num_bytes <= 0:
        return
    with _LOCK:
        now = _now()
        data = _load_state()
        _prune_log(data, now)
        _maybe_reroll_caps(data, now)
        data["usage_log"].append([now, num_bytes])
        _save_state(data)


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
