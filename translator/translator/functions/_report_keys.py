from ..common.state import PACKAGE_DIR, DEFAULTS
import sys
import time


def _report_keys(action, done, total):
    """
    Prints a clean, single-line progress indicator like 'Adding Keys... [023/643]'.

    Always called once per completed key (never skipped/batched), and
    pauses briefly after each write so the counter is actually visible
    ticking up one-by-one (1, then 2, then 3, ...) instead of flashing by
    too fast to read on fast, local (non-network) commands like --add and
    --remove. See DEFAULTS['key_progress_delay'].
    """
    width = len(str(total)) if total > 0 else 1
    sys.stdout.write(f"\r{action} Keys... [{done:0{width}d}/{total}]".ljust(60))
    sys.stdout.flush()
    delay = DEFAULTS.get("key_progress_delay", 0)
    if delay:
        time.sleep(delay)
