"""--usage: show current translation usage against the hourly/daily caps,
and --cooldown: manually force a cooldown on top of them."""

import sys
import time

from ..common.ratelimit import status_report, set_manual_cooldown


def _clock(epoch):
    return time.strftime("%I:%M %p", time.localtime(epoch)).lstrip("0")


def _relative(epoch):
    secs = max(0, int(epoch - time.time()))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)

    units = [("d", d), ("h", h), ("m", m), ("s", s)]
    nonzero = [(label, val) for label, val in units if val]

    if not nonzero:
        return "0s"
    return " ".join(f"{val}{label}" for label, val in nonzero)


def _usage_line_pairs(report, now):
    """(label, value) pairs for whichever usage lines currently apply --
    shared between the one-shot print and the --live redraw so the two
    can't drift out of sync with each other. Reset/cooldown lines are
    computed fresh from `now` rather than the precomputed *_reset_str
    fields on `report`, since --live needs those to actually count down
    tick to tick rather than being frozen at whenever the report was
    fetched."""
    pairs = [
        ("Daily Usage", f"{report['day_pct']:.0f}%"),
        ("Hourly Usage", f"{report['hour_pct']:.0f}%"),
    ]
    # If nothing's currently counted in a window, its "reset" is just
    # `now` (see _next_reset_epoch) -- there's no pending reset to show,
    # so skip the line rather than printing a reset time that's already
    # passed.
    if report["day_reset_epoch"] > now:
        pairs.append(("Daily Reset", f"{_clock(report['day_reset_epoch'])} (in {_relative(report['day_reset_epoch'])})"))
    if report["hour_reset_epoch"] > now:
        pairs.append(("Hourly Reset", f"{_clock(report['hour_reset_epoch'])} (in {_relative(report['hour_reset_epoch'])})"))
    if report["cooldown_active"]:
        pairs.append(("Manual Cooldown",
                       f"Expires at {_clock(report['cooldown_until_epoch'])} (in {_relative(report['cooldown_until_epoch'])})"))
    return pairs


def _cmd_usage_live(minutes):
    """Redraws the usage report in place every 100ms for `minutes`
    minutes, so the reset/cooldown countdowns visibly tick down instead
    of requiring repeated --usage calls. Ctrl+C ends it early and cleanly
    (no traceback) since this is a passive view, not a run in progress."""
    if minutes <= 0:
        print("--live needs a positive number of minutes, e.g. --usage --live 2")
        return

    duration = minutes * 60.0
    tick_interval = 0.1
    start = time.time()
    first = True
    last_line_count = 0

    try:
        while time.time() - start < duration:
            now = time.time()
            report = status_report()  # cached internally -- cheap every 100ms
            lines = [f"\033[K  {label}: {value}" for label, value in _usage_line_pairs(report, now)]

            # Cursor-up by however many lines the PREVIOUS tick actually
            # drew, not a fixed count -- a reset/cooldown line can drop
            # out mid-run once its window rolls over, and moving up the
            # wrong amount would leave stray text behind or eat into
            # whatever printed before this view started.
            cursor_up = "" if first else f"\033[{last_line_count}F"
            first = False
            last_line_count = len(lines)

            sys.stdout.write(cursor_up + "\n".join(lines) + "\n")
            sys.stdout.flush()

            time.sleep(tick_interval)
    except KeyboardInterrupt:
        pass

    print()


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