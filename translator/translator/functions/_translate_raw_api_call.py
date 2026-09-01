from ..common import debug_log
from ..common.config_store import get_request_delay, warn_red
from ..common.ratelimit import reserve, record_extra, record_outage, RateLimitExceededError
import time
from ..common.translate import _LAST_REQUEST_TIME, _RATE_LIMIT_LOCK
from .get_translator import get_translator


def _translate_raw_api_call(google_code, text_to_send):
    """
    The actual network call, plus rate limiting and usage-cap reservation,
    given plain text that's already safe to send (no protected tokens
    embedded in it -- see _raw_translate_once below for why that matters).
    """
    global _LAST_REQUEST_TIME

    delay = get_request_delay()
    translator = get_translator(google_code)

    # Usage-cap enforcement: blocks (adaptive cooldown / hourly pause) as
    # needed, or raises RateLimitExceededError if the daily cap is
    # genuinely exhausted. Sized on the outgoing request text; the
    # response size is added afterwards via record_extra() once known.
    debug_log.log(f"reserve() -- {len(text_to_send.encode('utf-8'))} bytes, {google_code}")
    reserve(len(text_to_send.encode("utf-8")))
    debug_log.log(f"reserve() cleared -- {google_code}")

    with _RATE_LIMIT_LOCK:
        now = time.time()
        elapsed = now - _LAST_REQUEST_TIME
        if elapsed < delay:
            time.sleep(delay - elapsed)
        _LAST_REQUEST_TIME = time.time()

    # The network call itself -- deep_translator/requests has no timeout
    # configured anywhere in this codebase, so a stalled connection blocks
    # here indefinitely with no exception raised, meaning none of the
    # retry/outage/rate-limit machinery below ever sees it happen. If a
    # run looks frozen, this is the single most likely place: a "sending"
    # line here with no matching "received" line, sitting at a stale
    # timestamp, is the smoking gun.
    debug_log.log(f"sending -- {google_code}, {len(text_to_send)} chars")
    result = translator.translate(text_to_send)
    debug_log.log(f"received -- {google_code}, {len(result)} chars")
    record_extra(len(result.encode("utf-8")))
    return result
