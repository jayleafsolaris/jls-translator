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

# Thread-safe rate limiter variables (module-local: translate_value is the
# only place these are read or written).
_RATE_LIMIT_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0


class TranslationUnavailableError(RuntimeError):
    """Raised when Google Translate can't be reached."""
    pass


# Guards against multiple threads all hitting the same failure at once and
# each printing/exiting redundantly.
_STOP_LOCK = threading.Lock()
_STOPPED = False
_BATCH_LOG_LOCK = threading.Lock()
_BATCH_LOGGED = False


def get_translator(google_code):
    return GoogleTranslator(source="en", target=google_code)


def translate_value(google_code, text):
    global _LAST_REQUEST_TIME, _STOPPED
    if not text.strip():
        return text

    # If another thread already tripped the stop, don't even try.
    if _STOPPED:
        exc = TranslationUnavailableError("Google Translate does not appear to be available right now. Please try again later.")
        exc.is_root_cause = False  # this thread got preempted, not the actual failure
        raise exc

    protected, tokens = _protect(text)
    delay = get_request_delay()

    try:
        translator = get_translator(google_code)

        with _RATE_LIMIT_LOCK:
            now = time.time()
            elapsed = now - _LAST_REQUEST_TIME
            if elapsed < delay:
                time.sleep(delay - elapsed)
            _LAST_REQUEST_TIME = time.time()

        result = translator.translate(protected)
        return _restore(result, tokens)
    except Exception as e:
        message = "Google Translate does not appear to be available right now. Please try again later."
        with _STOP_LOCK:
            if not _STOPPED:
                _STOPPED = True
                preview = text if len(text) <= 300 else text[:300] + "...(truncated)"
                warn_red(
                    f"Translation failed for '{google_code}' ({e!r}).\n"
                    f"Text being translated when it failed:\n{preview!r}"
                )
                print(message)
        if threading.current_thread() is threading.main_thread():
            # Safe to exit the process directly here.
            sys.exit(1)
        # Otherwise this is a worker thread, where sys.exit() only kills
        # that thread, not the process. Propagate and let the main thread
        # (e.g. translate_many's as_completed loop) exit instead.
        exc = TranslationUnavailableError(message)
        exc.is_root_cause = True  # this thread's request is what actually failed
        raise exc from e


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
            translated = translate_value(google_code, combined)
        except TranslationUnavailableError as exc:
            # Only log the batch breakdown for the batch that actually
            # caused the failure -- other in-flight batches raise this
            # too (via the _STOPPED short-circuit above) once one batch
            # trips the stop, but they never touched the API and would
            # just add noise.
            if getattr(exc, "is_root_cause", False):
                with _BATCH_LOG_LOCK:
                    global _BATCH_LOGGED
                    if not _BATCH_LOGGED:
                        _BATCH_LOGGED = True
                        lines = [f"  [skeleton {i}] {skel!r}" for i, skel in batch]
                        warn_red("Batch that failed contained these items:\n" + "\n".join(lines))
            raise
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
            # One worker hit an unavailable service: cancel the rest and stop.
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

    return results
