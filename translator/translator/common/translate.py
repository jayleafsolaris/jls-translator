"""
Google-Translate wrapper: single-value translation (with placeholder
protection + rate limiting) and batched multi-value translation.
"""

import concurrent.futures
import sys
import threading
import time

from deep_translator import GoogleTranslator

from .state import DEFAULTS
from .config_store import get_request_delay, warn_red
from .text_protect import _protect, _restore

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

# Counts values that fell back to untranslated text (not a real outage),
# so translate_many can report a summary at the end instead of the user
# having to scroll back through every individual warning.
_fallback_lock = threading.Lock()
_fallback_count = 0


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


def _record_fallback():
    global _fallback_count
    with _fallback_lock:
        _fallback_count += 1


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

    # Exhausted retries for this one value.
    is_outage = _record_failure_and_check_streak()
    preview = text if len(text) <= 300 else text[:300] + "...(truncated)"

    if is_outage:
        message = "Google Translate does not appear to be available right now. Please try again later."
        warn_red(
            f"{FAILURE_STREAK_THRESHOLD} translations in a row failed for '{google_code}' -- "
            f"this looks like Google Translate is actually unavailable, not just one odd value. Stopping.\n"
            f"Most recent failure ({last_err!r}) was on:\n{preview!r}"
        )
        print(message)
        if threading.current_thread() is threading.main_thread():
            sys.exit(1)
        raise TranslationUnavailableError(message) from last_err

    # Isolated quirk, not (yet) an outage -- log it and move on with the
    # original text rather than losing the rest of the run over one value.
    _record_fallback()
    warn_red(
        f"Could not translate for '{google_code}' after {DEFAULTS['max_retries']} attempts "
        f"({last_err!r}); leaving this one value untranslated:\n{preview!r}"
    )
    return text


def translate_many(google_code, texts, max_workers, progress_cb=None):
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

    # Dedupe by "skeleton" -- the value with its protected tokens
    # (%1$s-style placeholders, section-sign color codes, {key.path}-style
    # cross-references, etc) swapped out. Values that only differ in their
    # token content (e.g. eleven "{item.roe_lib:disc_X} Blueprint" lines
    # that only differ by which disc is named) collapse to the SAME
    # skeleton, so they only need to be translated once -- the per-item
    # tokens get spliced back into that one translated result afterward,
    # with zero extra API calls. This also avoids sending Google a batch
    # of near-identical repeated lines, which can trip its spam/repetition
    # detection and come back as an empty TranslationNotFound response.
    skeleton_to_members = {}   # skeleton -> list of (idx, tokens)
    skeleton_order = []        # first-seen order, for stable batching
    for idx in valid_indices:
        text_clean = texts[idx].replace('\n', '__NL__')
        skeleton, tokens = _protect(text_clean)
        if skeleton not in skeleton_to_members:
            skeleton_to_members[skeleton] = []
            skeleton_order.append(skeleton)
        skeleton_to_members[skeleton].append((idx, tokens))

    unique_skeletons = skeleton_order
    skeleton_results = [None] * len(unique_skeletons)

    def values_in_skeleton(skel_idx):
        return len(skeleton_to_members[unique_skeletons[skel_idx]])

    # Batch configurations -- sized against skeleton length (what's
    # actually sent to Google), so token-heavy values pack more densely
    # per request than they would using their full original length.
    MAX_BATCH_CHARS = 2500
    batches = []
    current_batch = []
    current_len = 0

    MIN_BATCH_FLOOR = 8
    desired_min_batches = min(len(unique_skeletons), MIN_BATCH_FLOOR)
    target_batch_count = min(len(unique_skeletons), max(max_workers, desired_min_batches))
    items_per_batch = max(1, -(-len(unique_skeletons) // target_batch_count))  # ceil div

    for skel_idx, skeleton in enumerate(unique_skeletons):
        if current_batch and (
            current_len + len(skeleton) > MAX_BATCH_CHARS
            or len(current_batch) >= items_per_batch
        ):
            batches.append(current_batch)
            current_batch = []
            current_len = 0

        current_batch.append((skel_idx, skeleton))
        current_len += len(skeleton) + 1  # +1 for the joining \n

    if current_batch:
        batches.append(current_batch)

    done_count = len(texts) - len(valid_indices)

    def translate_batch_worker(batch):
        # We join by newline. Google Translator translates sentences separately and natively returns them separated by \n
        combined = "\n".join(skel for _, skel in batch)

        try:
            translated = _raw_translate_once(google_code, combined)
            _record_success()
        except TranslationUnavailableError:
            raise
        except Exception:
            # Combined attempt failed. Rather than retrying the whole
            # (potentially large) combined blob, fall back to translating
            # this batch's skeletons individually -- translate_value
            # handles retries, the untranslated-fallback for isolated
            # quirks, and outage-streak detection for each one.
            completed_values = 0
            for skel_idx, skel in batch:
                res = translate_value(google_code, skel)
                skeleton_results[skel_idx] = res
                completed_values += values_in_skeleton(skel_idx)
            return completed_values

        lines = [line.replace('\r', '') for line in translated.split('\n')]

        completed_values = 0
        # Perfect split match
        if len(lines) == len(batch):
            for i, (skel_idx, _) in enumerate(batch):
                skeleton_results[skel_idx] = lines[i]
                completed_values += values_in_skeleton(skel_idx)
        else:
            # Fallback: if translation split structure shifted, do them independently
            for skel_idx, skel in batch:
                res = translate_value(google_code, skel)
                skeleton_results[skel_idx] = res
                completed_values += values_in_skeleton(skel_idx)
        return completed_values

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

    # Fan each translated skeleton back out to every original value that
    # shared it, splicing in that value's OWN tokens (not whichever
    # member happened to be translated) and restoring __NL__ to a real
    # newline.
    for skel_idx, skeleton in enumerate(unique_skeletons):
        translated_skeleton = skeleton_results[skel_idx]
        for idx, tokens in skeleton_to_members[skeleton]:
            results[idx] = _restore(translated_skeleton, tokens).replace('__NL__', '\n')

    if _fallback_count:
        print(f"({_fallback_count} value(s) could not be translated after retries and were left as-is.)")

    return results