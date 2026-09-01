from ..common import debug_log
from ..common.config_store import get_request_delay, warn_red
import time
from ..common.ratelimit import RateLimitExceededError, _DAY_SECONDS, _HOUR_SECONDS, _LOCK
from ._adaptive_cooldown import _adaptive_cooldown
from ._format_secs import _format_secs
from ._load_state import _load_state
from ._maybe_reroll_caps import _maybe_reroll_caps
from ._next_reset_epoch import _next_reset_epoch
from ._now import _now
from ._prune_log import _prune_log
from ._save_state import _save_state
from ._usage_within import _usage_within


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
