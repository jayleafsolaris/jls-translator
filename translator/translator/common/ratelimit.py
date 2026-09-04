"""
Network usage rate limiting for translation requests.

Tracks bytes sent to (and received from) Google Translate as a SLIDING
window log -- each request is logged as (timestamp, bytes), and "usage
this hour" / "usage today" is always the sum of whatever's still inside
the trailing 60-minute / 24-hour window. This is deliberate: with a fixed
bucket that only resets at a fixed clock boundary, running --update
in the middle of an existing window doesn't move the reset countdown at
all (it just adds to a bucket that resets whenever it resets, regardless
of when the most recent activity happened) -- which reads as "the
countdown is frozen." With a sliding window anchored to the *most
recent* logged request (see _next_reset_epoch()), every new request
pushes the reset countdown further out, so it always reflects how
recently the tool was actually used instead of a timestamp frozen
from whenever the state file was first created.

Hard caps (bytes, KB = 1000 bytes) are LEARNED, not hardcoded -- there's
no documented real quota for the unofficial endpoint deep_translator
hits, so the only trustworthy way to know how much can actually be sent
is to watch what actually happens:

  - GROW the cap when a whole hour/day window finishes with real demand
    (usage got pushed close to the current ceiling) and nothing went
    wrong -- i.e. a bigger job needed more room and Google didn't
    object, so there was headroom to spare. This is what makes the cap
    track actual job sizes automatically, without reading any job
    estimate directly: a bigger job naturally produces more usage,
    which naturally earns more room over time.
  - SHRINK the cap hard when a genuine outage was detected during the
    window (see translate.py's FAILURE_STREAK_THRESHOLD and this
    module's record_outage()) -- real evidence Google itself pushed
    back, as opposed to merely bumping into our own self-imposed
    ceiling (which is expected and not penalized).

See _adjust_cap()/_maybe_reroll_caps() below for the actual mechanics.
The _INITIAL_*_CAP_RANGE constants only seed a brand-new state file
before anything has been learned yet; _MIN_*_CAP/_MAX_*_CAP are sanity
backstops so growth/shrinkage can't run away to a degenerate value, not
ongoing hardcoded limits themselves.

A per-run "job profile" (how many bytes --create/--update still expects
to send) additionally lets the cooldown between individual requests
adapt within a single run: if the remaining work fits inside what's left
of the current budget, the cooldown stays at the normal configured
request delay; if it's on track to blow past that budget, the cooldown
stretches out proportionally.

On top of the automatic caps, --usage --24hr <hours> lets you manually
force a hard cooldown (1-72 hours) that blocks every translation request
until it lifts, independent of the hourly/daily budgets.
"""
import json
import random
import threading
import time
from .state import PACKAGE_DIR
from .config_store import get_request_delay, warn_red
from . import debug_log
_INITIAL_HOURLY_CAP_RANGE = (100_000, 1_500_000)   # 100 KB - 1.5 MB seed
_INITIAL_DAILY_CAP_RANGE = (4_500_000, 5_000_000)   # 4.5 MB - 5.0 MB seed
_MIN_HOUR_CAP = 150_000
_MAX_HOUR_CAP = 1_500_000
_MIN_DAY_CAP = 4_500_000
_MAX_DAY_CAP = 5_000_000
_GROWTH_FACTOR = 1.15
_SHRINK_FACTOR = 0.5
_GROWTH_UTILIZATION_THRESHOLD = 0.6
_JITTER_FRACTION = 0.05
_HOUR_SECONDS = 1.5 * 60 * 60
_DAY_SECONDS = 24 * 60 * 60
_MANUAL_COOLDOWN_MIN_HOURS = 1
_MANUAL_COOLDOWN_MAX_HOURS = 72
_MAX_COOLDOWN_MULTIPLIER = 20
_STATE_FILE = PACKAGE_DIR / ".ratelimit_state.json"
_LOCK = threading.Lock()
_job_remaining_keys = 0
_job_remaining_bytes = 0
_cache_lock = threading.Lock()
_cached_report = None
_cached_report_time = 0.0
_CACHE_TTL_SECONDS = 1.0
class RateLimitExceededError(RuntimeError):
    """Raised when the daily cap, or a manually-set cooldown, blocks a
    request outright. Callers should treat this like an outage: save
    progress and stop, so --continue can resume once it lifts."""
    pass
from ..functions._adaptive_cooldown import _adaptive_cooldown
from ..functions._adjust_cap import _adjust_cap
from ..functions._default_state import _default_state
from ..functions._format_secs import _format_secs
from ..functions._load_state import _load_state
from ..functions._maybe_reroll_caps import _maybe_reroll_caps
from ..functions._next_reset_epoch import _next_reset_epoch
from ..functions._now import _now
from ..functions._prune_log import _prune_log
from ..functions._save_state import _save_state
from ..functions._usage_within import _usage_within
from ..functions.clear_manual_cooldown import clear_manual_cooldown
from ..functions.record_extra import record_extra
from ..functions.record_outage import record_outage
from ..functions.reserve import reserve
from ..functions.set_job_profile import set_job_profile
from ..functions.set_manual_cooldown import set_manual_cooldown
from ..functions.status_report import status_report
