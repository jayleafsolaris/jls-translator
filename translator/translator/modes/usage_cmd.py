"""--usage: show current translation usage against the hourly/daily caps,
and --cooldown: manually force a cooldown on top of them."""

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
    if len(nonzero) == 1:
        return f"{nonzero[0][1]}{nonzero[0][0]}"
    first_label, first_val = nonzero[0]
    second_label, second_val = nonzero[1]
    return f"{first_val}{first_label} {second_val}{second_label}"


def cmd_usage(cooldown_hours=None):
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
        return

    report = status_report(use_cache=False)
    now = time.time()

    print(f"Daily Usage: {report['day_pct']:.0f}%")
    print(f"Hourly Usage: {report['hour_pct']:.0f}%")

    # If nothing's currently counted in a window, its "reset" is just
    # `now` (see _next_reset_epoch) -- there's no pending reset to show,
    # so skip the line rather than printing a reset time that's already
    # passed.
    if report["day_reset_epoch"] > now:
        print(f"Daily Reset: {_clock(report['day_reset_epoch'])} (in {report['day_reset_str']})")
    if report["hour_reset_epoch"] > now:
        print(f"Hourly Reset: {_clock(report['hour_reset_epoch'])} (in {report['hour_reset_str']})")

    if report["cooldown_active"]:
        print(f"Manual Cooldown: active until {_clock(report['cooldown_until_epoch'])} "
              f"(in {report['cooldown_reset_str']})")