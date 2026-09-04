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
class SmoothProgress:
    """
    Eases a progress bar's displayed value toward the latest real ("target")
    value instead of jumping straight to it.

    Real targets only arrive in chunks (once per finished network batch),
    so between two updates -- while a request is in flight, rate-limited,
    or cooling down -- the bar would otherwise catch up within
    catch_up_seconds and then sit dead flat for however long the next
    batch takes, which reads as "frozen"/laggy even though work is still
    happening. Once caught up, if no new (higher) target has arrived for
    stall_creep_after seconds and real work remains, this creeps the shown
    value forward slowly on its own -- capped at just under one whole
    percent of this instance's own key_total (floored at 0.9 units so
    small totals, e.g. a typical --update run's handful of changed keys,
    behave exactly as before), so it never visually claims a large chunk
    of real, unfinished work as done. Any real update snaps the ramp back
    to normal, ceiling-free motion toward the new target.

    That floor matters more than it looks: a caller with a small
    key_total (--update) needs a small absolute ceiling to stay honest,
    but a caller composing many per-item SmoothProgress instances into one
    larger displayed percentage (--create, one instance per language,
    folded into an overall-run percentage) needs the ceiling to scale with
    its own key_total -- a flat +0.9 units is a meaningfully large nudge
    against a total of 10, but is completely invisible against a total in
    the hundreds once diluted into that outer percentage, and reaches its
    tiny ceiling in about 6s regardless, then sits dead flat for however
    much longer the real stall runs. Scaling by key_total keeps both cases
    honest while keeping both visibly alive for the length of a real stall
    instead of just its first few seconds.
    """

    def __init__(self, key_total, render, tick_interval=0.08, catch_up_seconds=1.0,
                 stall_creep_after=1.2, creep_rate=0.15, creep_ceiling_fraction=0.02):
        self.key_total = key_total
        self._render = render  # callable(shown_key_idx)
        self._tick_interval = tick_interval
        self._ticks_to_catch_up = max(1, round(catch_up_seconds / tick_interval))
        self._target = 0
        self._shown = 0.0
        self._step = 0  # fixed per-tick increment for the current linear ramp
        self._stall_creep_after = stall_creep_after
        self._creep_rate = creep_rate  # phantom units/sec while stalled
        self._creep_ceiling = max(0.9, key_total * creep_ceiling_fraction)
        self._last_target_update = time.time()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, target):
        """Called (possibly from multiple worker threads) with the latest known progress."""
        with self._lock:
            if target > self._target:
                self._target = target
                self._last_target_update = time.time()
                # A plain per-tick fraction of the gap -- not rounded up to
                # a minimum of 1 -- so even a gap of a single key still
                # eases smoothly across the full catch_up_seconds window
                # instead of snapping there in one tick (which is what a
                # `max(1, ...)` floor here used to force for small gaps,
                # the common case during --update).
                gap = target - self._shown
                self._step = gap / self._ticks_to_catch_up

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                target = self._target
                shown = self._shown
                step = self._step
                stalled_for = time.time() - self._last_target_update
            if shown < target:
                shown = min(target, shown + step)
                with self._lock:
                    self._shown = shown
            elif stalled_for > self._stall_creep_after and target < self.key_total:
                # Caught up to the last real update but more work remains,
                # and nothing new has landed in a while -- nudge forward
                # slowly so the display keeps moving instead of stalling.
                creep_ceiling = target + self._creep_ceiling
                if shown < creep_ceiling:
                    shown = min(creep_ceiling, shown + self._creep_rate * self._tick_interval)
                    with self._lock:
                        self._shown = shown
            # Render every tick regardless of whether `shown` itself moved.
            # The caller's render function also recomputes elapsed time from
            # time.time() -- if we only rendered on progress changes, that
            # clock would freeze the instant creep tops out (or during a
            # long rate-limit sleep), even though real time keeps passing.
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
from ..functions._ask_continue import _ask_continue
from ..functions._convert_base_vars import _convert_base_vars
from ..functions._human_size import _human_size
from ..functions._report import _report
from ..functions._report_finishing import _report_finishing
from ..functions._report_keys import _report_keys
from ..functions.base_fingerprint import base_fingerprint
from ..functions.clear_progress import clear_progress
from ..functions.format_duration import format_duration
from ..functions.load_base import load_base
from ..functions.load_progress import load_progress
from ..functions.save_progress import save_progress
from ..functions.sync_en_us_from_base import sync_en_us_from_base
