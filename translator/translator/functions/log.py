import json
import threading
import time
from ..common.debug_log import _enabled, _entries, _lock
from .debug_log_path import debug_log_path


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
