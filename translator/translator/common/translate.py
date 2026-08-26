"""
Google-Translate wrapper: single-value translation (with placeholder
protection + rate limiting) and batched multi-value translation.
"""

import concurrent.futures
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
from .text_protect import _protect, _restore, split_segments, join_segments

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
# long run never fake-trigger a stop.
FAILURE_STREAK_THRESHOLD = 5

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


def get_translator(google_code):
    return GoogleTranslator(source="en", target=google_code)


def _raw_translate_once(google_code, text):
    """One real attempt against Google -- no retries, no fallback, raises
    on failure. Also short-circuits immediately if a prior failure streak
    already declared the service unavailable, so threads stop hammering a
    dead service once that's been detected."""
    global _LAST_REQUEST_TIME

    if _STOPPED:
        raise TranslationUnavailableError(
            "Google Translate does not appear to be available right now. Please try again later."
        )

    protected, tokens = _protect(text)
    delay = get_request_delay()
    translator = get_translator(google_code)

    with _RATE_LIMIT_LOCK:
        now = time.time()
        elapsed = now - _LAST_REQUEST_TIME
        if elapsed < delay:
            time.sleep(delay - elapsed)
        _LAST_REQUEST_TIME = time.time()

    result = translator.translate(protected)
    return _restore(result, tokens)


def translate_value(google_code, text):
    """
    Translates a single string. Retries a few times on failure
    (DEFAULTS['max_retries']); if it still won't go through, that failure
    is weighed against the run's overall failure streak rather than
    treated as fatal on its own:

    - If this looks like an isolated quirk (the run has otherwise been
      succeeding), the ORIGINAL untranslated text is returned so one bad
      value doesn't take down everything else, and a note is logged.
    - If failures have been happening back-to-back (FAILURE_STREAK_THRESHOLD
      in a row with no successes between them), that's treated as Google
      actually being unavailable, and the whole run stops.
    """
    if not text.strip():
        return text

    last_err = None
    for attempt in range(DEFAULTS["max_retries"]):
        try:
            result = _raw_translate_once(google_code, text)
            _record_success()
            return result
        except TranslationUnavailableError:
            # Streak threshold already tripped by another thread -- no
            # point retrying, this run is stopping.
            raise
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))

    # Exhausted retries for this one value -- always counts as a fatal
    # error for this value, whether or not it also trips the outage
    # streak check below.
    preview = text if len(text) <= 300 else text[:300] + "...(truncated)"
    is_outage = _record_failure_and_check_streak()
    _record_fallback(preview, last_err)

    if is_outage:
        message = "Google Translate does not appear to be available right now. Please try again later."
        warn_red(message)
        warn_red(f"Fatal Errors: {_fallback_count}")
        if threading.current_thread() is threading.main_thread():
            sys.exit(1)
        raise TranslationUnavailableError(message) from last_err

    # Isolated quirk, not (yet) an outage -- already recorded above.
    # Nothing prints here: translate_many prints a single "Fatal Errors: #"
    # line for the whole call at the very end, instead of anything
    # mid-run.
    return text


def translate_many(google_code, texts, max_workers, progress_cb=None):
    results = [None] * len(texts)
    if not texts:
        return results

    # Snapshot the fallback log too (same reasoning as the count baseline
    # above) so the block below only reports fragments from THIS call.
    fallback_baseline = _fallback_count

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
        except Exception:
            # Combined attempt failed. Rather than retrying the whole
            # (potentially large) combined blob, fall back to translating
            # this batch's fragments individually -- translate_value
            # handles retries, the untranslated-fallback for isolated
            # quirks, and outage-streak detection for each one.
            completed_values = 0
            for seg in batch:
                res = translate_value(google_code, seg)
                completed_values += resolve_segment(seg, res)
            return completed_values

        lines = [line.replace('\r', '') for line in translated.split('\n')]

        completed_values = 0
        # Perfect split match
        if len(lines) == len(batch):
            for i, seg in enumerate(batch):
                completed_values += resolve_segment(seg, lines[i])
        else:
            # Fallback: if translation split structure shifted, do them independently
            for seg in batch:
                res = translate_value(google_code, seg)
                completed_values += resolve_segment(seg, res)
        return completed_values

    if batches:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(translate_batch_worker, b) for b in batches]
            try:
                for fut in concurrent.futures.as_completed(futures):
                    done_count += fut.result()
                    if progress_cb:
                        progress_cb(done_count)
            except TranslationUnavailableError:
                # Failure streak crossed the outage threshold: cancel the
                # rest and stop, rather than continuing to hammer a dead
                # service batch after batch.
                for f in futures:
                    f.cancel()
                ex.shutdown(wait=True, cancel_futures=True)
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

    fallback_this_call = _fallback_count - fallback_baseline
    if fallback_this_call:
        warn_red(f"Fatal Errors: {fallback_this_call}")

    return results