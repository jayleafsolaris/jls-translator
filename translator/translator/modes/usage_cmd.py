"""--usage: show current translation usage against the hourly/daily caps."""

import time

from ..common.ratelimit import status_report


def cmd_usage():
    report = status_report(use_cache=False)

    day_clock = time.strftime("%I:%M %p", time.localtime(report["day_reset_epoch"])).lstrip("0")
    hour_clock = time.strftime("%I:%M %p", time.localtime(report["hour_reset_epoch"])).lstrip("0")

    print(f"Daily Usage: {report['day_pct']:.0f}%")
    print(f"Hourly Usage: {report['hour_pct']:.0f}%")
    print(f"Daily Reset: {day_clock} (in {report['day_reset_str']})")
    print(f"Hourly Reset: {hour_clock} (in {report['hour_reset_str']})")