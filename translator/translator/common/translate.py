"""
Google-Translate wrapper: single-value translation (with placeholder
protection + rate limiting) and batched multi-value translation.
"""
import concurrent.futures
import random
import sys
import threading
import time
import requests
from deep_translator import GoogleTranslator
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
from deep_translator import GoogleTranslator
from .state import DEFAULTS
from .config_store import get_request_delay, warn_red
from .text_protect import split_segments, join_segments
from .ratelimit import reserve, record_extra, record_outage, RateLimitExceededError
from . import debug_log
_RATE_LIMIT_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0
class TranslationUnavailableError(RuntimeError):
    """Raised only when Google Translate looks genuinely unreachable -- see
    FAILURE_STREAK_THRESHOLD below -- not for a single value/batch quirk."""
    pass
FAILURE_STREAK_THRESHOLD = 25
_streak_lock = threading.Lock()
_consecutive_failures = 0
_STOPPED = False
_fallback_lock = threading.Lock()
_fallback_count = 0
_fallback_log = []  # list of (preview, error_repr) for this whole process
from ..functions._handle_rate_limit_stop import _handle_rate_limit_stop
from ..functions._raw_translate_once import _raw_translate_once
from ..functions._record_failure_and_check_streak import _record_failure_and_check_streak
from ..functions._record_fallback import _record_fallback
from ..functions._record_success import _record_success
from ..functions._translate_raw_api_call import _translate_raw_api_call
from ..functions._translate_segments_deferred import _translate_segments_deferred
from ..functions.get_fallback_count import get_fallback_count
from ..functions.get_fallback_log import get_fallback_log
from ..functions.get_translator import get_translator
from ..functions.reset_outage_state import reset_outage_state
from ..functions.translate_many import translate_many
from ..functions.translate_value import translate_value
