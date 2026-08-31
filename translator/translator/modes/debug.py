"""--debug: combine with another mode (--create/--update/--add/--remove/
--continue/etc.) to turn on timestamped diagnostic logging for that run --
see common/debug_log.py for what actually gets logged and why.

Used alone (--debug with no other mode), it's a one-off command instead:
resets __debug-log.json to a clean empty state in the current project
folder, creating the file if it doesn't already exist. Run this before
reproducing an issue with --debug combined with another mode, so that
run's log starts from a clean slate rather than mixing in with whatever
an earlier session already logged.
"""

from ..common import debug_log


def cmd_debug():
    path = debug_log.debug_log_path()
    path.write_text("[]", encoding="utf-8")
    print(f"Debug log reset: {path}")
    print("Combine --debug with another mode (e.g. --update --debug) to log that run.")
