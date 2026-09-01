from ..common.ratelimit import status_report, set_manual_cooldown
import sys
import time
from ._usage_line_pairs import _usage_line_pairs


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
