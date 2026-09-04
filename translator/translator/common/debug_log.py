"""
--debug: lightweight diagnostic logging, off (and effectively free) by
default -- a single boolean check per call site.

Combine --debug with another mode (e.g. --update --debug, --create
--debug) to print a timestamped line for every notable step
common/translate.py and common/ratelimit.py take: reserve() waits, the
actual outbound Google request/response, batch submission/completion,
deferred retries, outages. The point is specifically diagnosing a run
that looks "frozen" -- progress bar stopped moving, nothing printing --
by pinning down the exact call it's stuck inside and the exact moment it
started, since a hung network call raises no exception and so triggers
none of the existing retry/outage machinery.

Every entry is written to disk immediately (not buffered until the run
finishes), specifically so the log still has everything up to the hang
even if the process has to be force-killed rather than exiting cleanly.

Used alone (--debug with no other mode), it's a one-off command: see
cmd_debug() in modes/debug.py -- resets __debug-log.json to a clean
empty state in the current project folder (next to base) so the next
--debug run's log isn't mixed in with an earlier session's.
"""
import json
import threading
import time
from . import state
_enabled = False
_lock = threading.Lock()
_entries = []  # list of {"time", "epoch", "thread", "message"}
from ..functions.debug_log_path import debug_log_path
from ..functions.enable import enable
from ..functions.is_enabled import is_enabled
from ..functions.log import log
