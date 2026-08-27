"""
Progress tracking (resumable --create/--update/--add/--remove/--delete
runs), base-file loading, and the various in-place progress renderers
shared by the mode commands.
"""

import hashlib
import json
import re
import sys
import threading
import time

from . import state
from .state import PACKAGE_DIR, DEFAULTS
from .lang_io import parse_lang, write_lang, strip_comments_for_output

def base_fingerprint(base_values):
    blob = json.dumps(base_values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def load_progress():
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
             return None
    return None

def save_progress(command, completed, fingerprint, elapsed_time=0.0):
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    path.write_text(
        json.dumps({
            "command": command,
            "completed": completed,
            "fingerprint": fingerprint,
            "elapsed_time": elapsed_time
        }, indent=2),
        encoding="utf-8",
    )

def clear_progress():
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    if path.exists():
        path.unlink()
        return True
    return False

def format_duration(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m {secs}s"

def _convert_base_vars(lines):
    """Converts user-friendly {1} syntax in base to Bedrock's %1$s."""
    out = []
    for line in lines:
        if line[0] == "entry":
            # Replaces {1} -> %1$s, {2} -> %2$s, etc.
            new_val = re.sub(r"\{(\d+)\}", r"%\1$s", line[2])
            out.append(("entry", line[1], new_val, line[3]))
        else:
            out.append(line)
    return out

def load_base():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.exists():
        sys.exit(f"Error: base file not found (expected '{DEFAULTS['base_lang']}' in {state.SCRIPT_DIR})")
    lines = parse_lang(base_path)
    # Process the lines to convert `{n}` to `%n$s` in memory
    return _convert_base_vars(lines)

def sync_en_us_from_base(base_lines):
    en_us_path = state.SCRIPT_DIR / "en_US.lang"
    # Strip every comment line (section headers, notes, disabled/commented
    # entries, and the hidden --update count marker) before mirroring base
    # into en_US.lang -- comments belong to base only and should never
    # show up in a generated, user-facing .lang file.
    write_lang(en_us_path, strip_comments_for_output(list(base_lines)))
    return en_us_path

def _report(lang_idx, lang_total, code, key_idx, key_total, start_time=None, prev_elapsed=0.0, note=""):
    overall_pct = ((lang_idx - 1) + (key_idx / key_total if key_total else 1)) / lang_total * 100

    if start_time is not None:
        time_str = format_duration(prev_elapsed + (time.time() - start_time))
    else:
        time_str = format_duration(prev_elapsed)

    is_final = lang_idx >= lang_total and key_idx >= key_total
    if is_final:
        line = f"[{lang_idx}/{lang_total}] {overall_pct:5.1f}% - Time: {time_str}"
    else:
        line = f"[{lang_idx}/{lang_total}] {overall_pct:5.1f}% ({code}) - Time: {time_str}"
    if note:
        line += f" {note}"
    sys.stdout.write("\r" + line.ljust(85))
    sys.stdout.flush()


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


class SmoothProgress:
    """
    Eases a progress bar's displayed value toward the latest real ("target")
    value instead of jumping straight to it.
    """

    def __init__(self, key_total, render, tick_interval=0.08, catch_up_seconds=1.0):
        self.key_total = key_total
        self._render = render  # callable(shown_key_idx)
        self._tick_interval = tick_interval
        self._ticks_to_catch_up = max(1, round(catch_up_seconds / tick_interval))
        self._target = 0
        self._shown = 0
        self._step = 0  # fixed per-tick increment for the current linear ramp
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, target):
        """Called (possibly from multiple worker threads) with the latest known progress."""
        with self._lock:
            if target > self._target:
                self._target = target
                # Recompute a fresh, constant step so the climb from here to
                # this new target is a straight line, not a shrinking one.
                gap = target - self._shown
                self._step = max(1, -(-gap // self._ticks_to_catch_up))  # ceil division

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                target = self._target
                shown = self._shown
                step = self._step
            if shown < target:
                shown = min(target, shown + step)
                with self._lock:
                    self._shown = shown
                self._render(shown)
            self._stop.wait(self._tick_interval)

    def finish(self):
        """Ease any remaining gap up to 100%, then stop the ticker thread."""
        self.update(self.key_total)
        # Let the background ticker keep easing toward 100% on its own
        # schedule instead of snapping, then stop it once it arrives.
        while True:
            with self._lock:
                shown = self._shown
            if shown >= self.key_total:
                break
            time.sleep(self._tick_interval)
        self._stop.set()
        self._thread.join(timeout=1.0)


def _ask_continue(code):
    while True:
        answer = input(f"\nFinished {code}. Continue to next? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")




def _human_size(num_bytes):
    for unit in ("B", "KB", "MB"):
        if num_bytes < 1024:
            return f"{num_bytes:.0f}{unit}" if unit == "B" else f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}GB"
