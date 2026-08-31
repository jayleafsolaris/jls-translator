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


def enable():
    """Called from cli.py when --debug is combined with another mode."""
    global _enabled
    _enabled = True


def is_enabled():
    return _enabled


def debug_log_path():
    """__debug-log.json lives in the current project folder -- the same
    directory as base -- not next to the installed package, so it's easy
    to find and doesn't get mixed up across different projects sharing
    one install (see common/state.py's PACKAGE_DIR vs SCRIPT_DIR)."""
    return state.SCRIPT_DIR / "__debug-log.json"


def log(message):
    """
    Timestamped debug line. No-ops (one boolean check) unless --debug
    was passed this run. Prints immediately with an exact :hh:mm:ss:
    timestamp and appends to __debug-log.json right away -- never held
    in memory only until the end, since a frozen run may never reach
    "the end".
    """
    if not _enabled:
        return

    now = time.time()
    ts = time.strftime("%H:%M:%S", time.localtime(now))
    thread_name = threading.current_thread().name

    print(f":{ts}: [{thread_name}] {message}", flush=True)

    with _lock:
        _entries.append({"time": ts, "epoch": now, "thread": thread_name, "message": message})
        entries_snapshot = list(_entries)

    try:
        debug_log_path().write_text(json.dumps(entries_snapshot, indent=2), encoding="utf-8")
    except Exception:
        # Never let debug logging itself take down the run it's trying
        # to help diagnose.
        pass
