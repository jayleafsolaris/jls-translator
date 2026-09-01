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

# Overriding request headers to mimic a desktop browser
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})

from deep_translator import GoogleTranslator

from .state import DEFAULTS
from .config_store import get_request_delay, warn_red
from .text_protect import split_segments, join_segments
from .ratelimit import reserve, record_extra, record_outage, RateLimitExceededError
from . import debug_log

# Thread-safe rate limiter variables (module-local: _raw_translate_once is
# the only place these are read or written).
_RATE_LIMIT_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0


class TranslationUnavailableError(RuntimeError):
    """Raised only when Google Translate looks genuinely unreachable -- see
    FAILURE_STREAK_THRESHOLD below -- not for a single value/batch quirk."""
    pass


# --- Automatic outage detection -----------------------------------------
#
# A single value (or batch) failing doesn't necessarily mean Google
# Translate is down -- it might just be one oddly-shaped string tripping
# something on Google's end (seen in practice: a batch of near-identical
# placeholder-heavy lines returning TranslationNotFound). Retrying and
# falling back to leaving that one value untranslated handles that case
# without losing the rest of a run.
#
# What DOES indicate a real outage is failures happening back-to-back with
# no successes in between, regardless of what the content looks like --
# that's not "this string is weird", that's "nothing is getting through".
# Any success anywhere resets the streak, so scattered failures across a
# long run never fake-trigger a stop. The threshold is set high (25) on
# purpose: with deferred/shuffled retries spreading failures out across
# different fragments (see _translate_segments_deferred), 25 in a row with
# zero successes anywhere in the whole run is no longer plausible unless
# Google Translate is genuinely unreachable -- at which point the process
# ends completely (sys.exit(1) / re-raised TranslationUnavailableError)
# rather than continuing to burn through retries into the same wall.
FAILURE_STREAK_THRESHOLD = 25

_streak_lock = threading.Lock()
_consecutive_failures = 0
_STOPPED = False

# Counts (and logs details of) values that fell back to untranslated text
# (not a real outage). These are deferred rather than printed immediately
# -- translate_value used to print a warning the moment each one
# happened, which meant it could land mid-line in the middle of a live
# progress percentage. Collecting them here lets translate_many print a
# single "Fatal Errors: #" line at the very end instead.
_fallback_lock = threading.Lock()
_fallback_count = 0
_fallback_log = []  # list of (preview, error_repr) for this whole process


def _record_success():
    global _consecutive_failures
    with _streak_lock:
        _consecutive_failures = 0


def _record_failure_and_check_streak():
    """Increments the run's failure streak. Returns True if this failure
    just pushed it over FAILURE_STREAK_THRESHOLD (i.e. treat as a real
    outage), False if it's still within normal single-item quirk territory."""
    global _consecutive_failures, _STOPPED
    with _streak_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= FAILURE_STREAK_THRESHOLD and not _STOPPED:
            _STOPPED = True
            return True
        return False


def _record_fallback(preview, err):
    global _fallback_count
    with _fallback_lock:
        _fallback_count += 1
        _fallback_log.append((preview, err))


def reset_outage_state():
    """Clears the declared-outage flag and the consecutive-failure streak.

    _STOPPED otherwise latches True for the rest of the process once
    FAILURE_STREAK_THRESHOLD is crossed -- by design, so a single caller
    mid-run doesn't keep hammering a dead service. A caller that backs
    off on its own (e.g. --update's slow-down/retry handling) and wants
    to give Google a genuinely fresh attempt after waiting needs a way to
    lift that latch first; otherwise every retry would short-circuit
    straight back into TranslationUnavailableError without ever touching
    the network again."""
    global _consecutive_failures, _STOPPED
    with _streak_lock:
        _consecutive_failures = 0
        _STOPPED = False


def _handle_rate_limit_stop(err):
    """Shared handling for RateLimitExceededError wherever it surfaces:
    print the reason, note that progress is safe to resume from, and end
    the process from the main thread (mirrors how a genuine
    TranslationUnavailableError outage is handled below)."""
    warn_red(str(err))
    print("Progress has been saved -- run --continue once the usage window resets.")
    if threading.current_thread() is threading.main_thread():
        sys.exit(1)
    raise err


def get_translator(google_code):
    return GoogleTranslator(source="en", target=google_code)


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


def _raw_translate_once(google_code, text):
    """
    One real attempt against Google -- no retries, no fallback, raises
    on failure. Also short-circuits immediately if a prior failure streak
    already declared the service unavailable, so threads stop hammering a
    dead service once that's been detected.

    Protected tokens (color codes, %1$s-style placeholders, {key.path}
    cross-references, PUA glyphs) are split OUT of the text entirely
    before anything is sent to Google -- never embedded as an inline
    "@@PHn@@"-style marker for Google to (sometimes) mangle or silently
    drop as noise, which is how a token like a {key.path} cross-reference
    could previously vanish from the translated result. This mirrors the
    same split_segments()/join_segments() approach translate_many() uses
    for its batches.
    """
    if _STOPPED:
        raise TranslationUnavailableError(
            "Google Translate does not appear to be available right now. Please try again later."
        )

    text_clean = text.replace('\n', '__NL__')
    parts = split_segments(text_clean)
    distinct_text = list(dict.fromkeys(content for kind, content in parts if kind == "text"))

    if not distinct_text:
        # Nothing but tokens (e.g. a value that's just one {key.path}
        # cross-reference) -- nothing to actually translate.
        return join_segments(parts).replace('__NL__', '\n')

    combined = "\n".join(distinct_text)
    result = _translate_raw_api_call(google_code, combined)

    lines = [line.replace('\r', '') for line in result.split('\n')]
    if len(lines) == len(distinct_text):
        segment_results = dict(zip(distinct_text, lines))
    else:
        # Google's returned line count didn't line up with what was sent --
        # translate each distinct fragment on its own instead of guessing
        # at an alignment.
        segment_results = {seg: _translate_raw_api_call(google_code, seg) for seg in distinct_text}

    rebuilt = []
    for kind, content in parts:
        rebuilt.append(content if kind == "token" else segment_results.get(content, content))
    return "".join(rebuilt).replace('__NL__', '\n')


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


def translate_value(google_code, text):
    """
    Translates a single string in isolation (for any caller working with
    just one string outside a translate_many() batch). Delegates to the
    same deferred-retry machinery translate_many's batch fallback uses --
    see _translate_segments_deferred -- though with only one item in the
    pool there's nothing else to interleave with, so a failing value
    simply retries itself up to DEFAULTS['max_retries'] times before
    falling back to the original text.
    """
    if not text.strip():
        return text
    return _translate_segments_deferred(google_code, [text])[text]


def get_fallback_count():
    """Total number of values that fell back to untranslated text (real
    outages aside) across the whole process so far. Exposed so callers
    like --update can fold this into their own live progress display
    instead of translate_many announcing it mid-run itself."""
    return _fallback_count


def get_fallback_log():
    """Copy of the (preview, error) pairs behind get_fallback_count(), for
    callers that want to report specifics at the end of a run."""
    with _fallback_lock:
        return list(_fallback_log)


def translate_many(google_code, texts, max_workers, progress_cb=None):
    debug_log.log(f"translate_many start -- {google_code}, {len(texts)} values, {max_workers} workers")
    results = [None] * len(texts)
    if not texts:
        return results

    # Filter out empty strings beforehand to optimize network requests
    valid_indices = [i for i, t in enumerate(texts) if t.strip()]
    for i in range(len(texts)):
        if not texts[i].strip():
            results[i] = texts[i]

    if not valid_indices:
        if progress_cb:
            progress_cb(len(texts))
        return results

    # Split each value into alternating token/text pieces at TOKEN_PATTERN
    # boundaries (color codes, %1$s-style placeholders, {key.path}-style
    # cross-references, __NL__ newline markers). Tokens are carried through
    # completely unchanged and NEVER sent to Google -- only the plain-text
    # pieces are. This means a value like
    #   "{item.roe_lib:disc_x} Blueprint"
    # sends only "Blueprint" for translation, not a placeholder-laden
    # stand-in for the whole value. Previously tokens were replaced with an
    # inline "@@PHn@@" marker that still traveled to Google as part of the
    # request text -- harmless-looking alone, but a batch of many such
    # marker-heavy lines can look like repetitive noise to Google and
    # trigger an empty TranslationNotFound response.
    value_parts = {}   # idx -> list of ('token'|'text', content), in order
    for idx in valid_indices:
        text_clean = texts[idx].replace('\n', '__NL__')
        value_parts[idx] = split_segments(text_clean)

    # Unique plain-text fragments across ALL values, deduped by exact
    # content. A fragment shared across different keys (" by ", "Blueprint",
    # "Corrupted Disc") -- or repeated more than once within the same
    # value -- only gets translated once no matter how many places it's
    # used, and the result is spliced back into every one of them.
    segment_to_values = {}   # text -> set of idx that need it
    segment_order = []       # first-seen order, for stable batching
    value_remaining = {}     # idx -> count of distinct unresolved segments
    for idx, parts in value_parts.items():
        distinct_text = {content for kind, content in parts if kind == "text"}
        if not distinct_text:
            # Entirely tokens (e.g. a value that's just one {key.path}
            # cross-reference) -- nothing to translate, resolve immediately.
            results[idx] = join_segments(parts).replace('__NL__', '\n')
            continue
        value_remaining[idx] = len(distinct_text)
        for content in distinct_text:
            if content not in segment_to_values:
                segment_to_values[content] = set()
                segment_order.append(content)
            segment_to_values[content].add(idx)

    unique_segments = segment_order
    segment_results = {}  # text -> translated text

    # Batch configuration -- sized against the plain-text fragments
    # actually being sent (never the full original value, and never
    # token-laden), so requests pack more densely and cleanly than before.
    MAX_BATCH_CHARS = 2500
    batches = []
    current_batch = []
    current_len = 0

    if unique_segments:
        MIN_BATCH_FLOOR = 8
        desired_min_batches = min(len(unique_segments), MIN_BATCH_FLOOR)
        target_batch_count = min(len(unique_segments), max(max_workers, desired_min_batches))
        items_per_batch = max(1, -(-len(unique_segments) // target_batch_count))  # ceil div

        for seg in unique_segments:
            if current_batch and (
                current_len + len(seg) > MAX_BATCH_CHARS
                or len(current_batch) >= items_per_batch
            ):
                batches.append(current_batch)
                current_batch = []
                current_len = 0

            current_batch.append(seg)
            current_len += len(seg) + 1  # +1 for the joining \n

        if current_batch:
            batches.append(current_batch)

    # Values already resolved above (pure-token, no translation needed)
    # count toward done_count immediately, same as blank strings.
    done_count = len(texts) - len(valid_indices)
    done_count += sum(1 for idx in valid_indices if idx not in value_remaining)

    remaining_lock = threading.Lock()

    def resolve_segment(seg, translated):
        """Records a segment's translated result and returns how many
        original values just became fully resolved because of it (used
        only for progress_cb accounting -- the actual strings get rebuilt
        in one pass after every batch finishes, below)."""
        segment_results[seg] = translated
        newly_done = 0
        with remaining_lock:
            for idx in segment_to_values[seg]:
                value_remaining[idx] -= 1
                if value_remaining[idx] == 0:
                    newly_done += 1
        return newly_done

    def translate_batch_worker(batch):
        # We join by newline. Google Translator translates sentences separately and natively returns them separated by \n
        combined = "\n".join(batch)

        try:
            translated = _raw_translate_once(google_code, combined)
            _record_success()
        except TranslationUnavailableError:
            raise
        except RateLimitExceededError:
            # Daily usage cap exhausted -- propagate up so the caller
            # stops the whole run, same as a genuine outage, rather than
            # falling back to per-fragment retries into the same wall.
            raise
        except Exception:
            # Combined attempt failed. Rather than retrying the whole
            # (potentially large) combined blob, fall back to translating
            # this batch's fragments individually and deferred -- see
            # _translate_segments_deferred for retry/fallback/outage
            # handling across the whole batch at once.
            completed_values = 0
            translated_map = _translate_segments_deferred(google_code, batch)
            for seg in batch:
                completed_values += resolve_segment(seg, translated_map[seg])
            return completed_values

        lines = [line.replace('\r', '') for line in translated.split('\n')]

        completed_values = 0
        # Perfect split match
        if len(lines) == len(batch):
            for i, seg in enumerate(batch):
                completed_values += resolve_segment(seg, lines[i])
        else:
            # Fallback: if translation split structure shifted, do them
            # independently and deferred (same as the except-branch above).
            translated_map = _translate_segments_deferred(google_code, batch)
            for seg in batch:
                completed_values += resolve_segment(seg, translated_map[seg])
        return completed_values

    if batches:
        debug_log.log(f"submitting {len(batches)} batches -- {google_code}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(translate_batch_worker, b) for b in batches]
            try:
                for fut in concurrent.futures.as_completed(futures):
                    done_count += fut.result()
                    debug_log.log(f"batch done -- {done_count}/{len(valid_indices)} values resolved, {google_code}")
                    if progress_cb:
                        progress_cb(done_count)
            except (TranslationUnavailableError, RateLimitExceededError) as err:
                # Failure streak crossed the outage threshold, or the
                # daily usage cap was exhausted: cancel the rest and stop,
                # rather than continuing to hammer a dead/limited service
                # batch after batch.
                debug_log.log(f"stopping -- {type(err).__name__}: {err}")
                for f in futures:
                    f.cancel()
                ex.shutdown(wait=True, cancel_futures=True)
                if isinstance(err, RateLimitExceededError):
                    _handle_rate_limit_stop(err)
                # We're back on the main thread here, so sys.exit() actually
                # terminates the process instead of just the worker thread.
                sys.exit(1)
    elif progress_cb:
        progress_cb(done_count)

    # Final reconstruction: rebuild each value from its own ordered
    # token/text pieces, splicing in that piece's translated result --
    # tokens pass through completely untouched.
    for idx in valid_indices:
        if results[idx] is not None:
            continue  # already resolved above (pure-token value)
        rebuilt = []
        for kind, content in value_parts[idx]:
            if kind == "token":
                rebuilt.append(content)
            else:
                rebuilt.append(segment_results.get(content, content))
        results[idx] = "".join(rebuilt).replace('__NL__', '\n')

    return results
