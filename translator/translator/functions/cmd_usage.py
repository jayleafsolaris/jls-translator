from ..common.ratelimit import status_report, set_manual_cooldown
import time
from ._clock import _clock
from ._cmd_usage_live import _cmd_usage_live
from ._relative import _relative
from ._usage_line_pairs import _usage_line_pairs


def cmd_usage(cooldown_hours=None, live_minutes=None):
    if cooldown_hours is not None:
        clamped = max(1.0, min(72.0, cooldown_hours))
        now = time.time()
        until_epoch = set_manual_cooldown(cooldown_hours)
        requested_until = now + clamped * 3600
        note = ""
        if clamped != cooldown_hours:
            note = f" (requested {cooldown_hours:g}h, clamped to the 1-72h range)"
        if until_epoch > requested_until + 1:  # small slack for time elapsed mid-call
            print(f"An existing cooldown already runs later than {clamped:g}h -- left unchanged.")
        else:
            print(f"Cooldown enforced for {clamped:g}h{note}.")
        print(f"Translations are blocked until {_clock(until_epoch)} (in {_relative(until_epoch)}).")
        if live_minutes is None:
            return
        print()

    if live_minutes is not None:
        _cmd_usage_live(live_minutes)
        return

    report = status_report(use_cache=False)
    now = time.time()
    for label, value in _usage_line_pairs(report, now):
        print(f"{label}: {value}")
