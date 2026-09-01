from ..common.config_store import get_request_delay, warn_red
from ..common.ratelimit import reserve, record_extra, record_outage, RateLimitExceededError
from ..common.state import DEFAULTS
import random
import sys
import threading
from ..common.translate import TranslationUnavailableError, _fallback_count
from ._raw_translate_once import _raw_translate_once
from ._record_failure_and_check_streak import _record_failure_and_check_streak
from ._record_fallback import _record_fallback
from ._record_success import _record_success


def _translate_segments_deferred(google_code, segments):
    """
    Translates a list of distinct text fragments one at a time, deferring
    failures instead of retrying them back-to-back.

    A fragment that fails a real attempt is NOT immediately retried
    against the same request that just failed it -- it's put back into
    the pool, the whole remaining pool is shuffled, and a DIFFERENT
    fragment is tried next. Only after a fragment has failed
    DEFAULTS['max_retries'] times -- spread out like this rather than 3 in
    a row -- does it give up and fall back to its own original,
    untranslated text, exactly as before.

    This keeps the outage-streak detector meaningful: hammering one
    problem fragment 3x in a row used to manufacture its own miniature
    failure streak in isolation, indistinguishable from a real outage.
    Interleaving different fragments between attempts means repeated
    failures on the SAME fragment no longer masquerade as the whole
    service being down -- only genuinely widespread failures (every
    fragment in the pool failing) still trip FAILURE_STREAK_THRESHOLD.

    Streak/outage bookkeeping only happens once a fragment is fully
    exhausted (same as before) -- an intermediate, deferred attempt
    doesn't itself count against the streak, only a fragment that never
    recovers across all its attempts does.

    Returns {fragment: translated_text}.
    """
    max_attempts = DEFAULTS["max_retries"]
    pending = [seg for seg in segments if seg.strip()]
    results = {seg: seg for seg in segments if not seg.strip()}
    attempts = {seg: 0 for seg in pending}

    while pending:
        seg = pending.pop(0)
        try:
            results[seg] = _raw_translate_once(google_code, seg)
            _record_success()
        except TranslationUnavailableError:
            raise
        except RateLimitExceededError:
            # Daily usage cap exhausted -- stop the run the same way an
            # outage does, rather than deferring into the same wall.
            raise
        except Exception as e:
            attempts[seg] += 1
            if attempts[seg] < max_attempts:
                # Defer: a different fragment goes next, this one comes
                # back around later once the (shuffled) pool cycles to it.
                pending.append(seg)
                random.shuffle(pending)
                continue

            # Exhausted this fragment's attempts -- always counts as a
            # fatal error for it, whether or not it also trips the outage
            # streak check below.
            preview = seg if len(seg) <= 300 else seg[:300] + "...(truncated)"
            is_outage = _record_failure_and_check_streak()
            _record_fallback(preview, e)
            results[seg] = seg

            if is_outage:
                # Real evidence Google itself pushed back, as opposed to
                # merely hitting our own self-imposed ceiling -- teach the
                # learned hour/day caps in ratelimit.py to back off so
                # future runs don't push this hard again.
                record_outage()
                message = "Google Translate does not appear to be available right now. Please try again later."
                warn_red(message)
                warn_red(f"Fatal Errors: {_fallback_count}")
                if threading.current_thread() is threading.main_thread():
                    sys.exit(1)
                raise TranslationUnavailableError(message) from e

    return results
