"""
Google-Translate wrapper: single-value translation (with placeholder
protection + rate limiting) and batched multi-value translation.
"""

import concurrent.futures
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

def get_translator(google_code):
    return GoogleTranslator(source="en", target=google_code)


def translate_value(google_code, text):
    global _LAST_REQUEST_TIME
    if not text.strip():
        return text
    protected, tokens = _protect(text)
    last_err = None
    delay = get_request_delay()
    
    for attempt in range(DEFAULTS["max_retries"]):
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
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    warn_red(f"Translation failed for '{google_code}' after {DEFAULTS['max_retries']} attempts "
             f"({last_err!r}); falling back to untranslated text.")
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

    # Batch configurations
    MAX_BATCH_CHARS = 2500
    batches = []
    current_batch = []
    current_len = 0

    MIN_BATCH_FLOOR = 8
    desired_min_batches = min(len(valid_indices), MIN_BATCH_FLOOR)
    target_batch_count = min(len(valid_indices), max(max_workers, desired_min_batches))
    items_per_batch = max(1, -(-len(valid_indices) // target_batch_count))  # ceil div

    # Group strings into batches using newlines
    for idx in valid_indices:
        text_clean = texts[idx].replace('\n', '__NL__')

        if current_batch and (
            current_len + len(text_clean) > MAX_BATCH_CHARS
            or len(current_batch) >= items_per_batch
        ):
            batches.append(current_batch)
            current_batch = []
            current_len = 0

        current_batch.append((idx, text_clean))
        current_len += len(text_clean) + 1  # +1 for the joining \n

    if current_batch:
        batches.append(current_batch)

    done_count = len(texts) - len(valid_indices)

    def translate_batch_worker(batch):
        # We join by newline. Google Translator translates sentences separately and natively returns them separated by \n
        combined = "\n".join(t for _, t in batch)
        try:
            translated = translate_value(google_code, combined)
            lines = [line.replace('\r', '') for line in translated.split('\n')]
            
            # Perfect split match
            if len(lines) == len(batch):
                for i, (idx, _) in enumerate(batch):
                    results[idx] = lines[i].replace('__NL__', '\n')
            else:
                # Fallback: if translation split structure shifted, do them independently
                for idx, t in batch:
                    res = translate_value(google_code, t)
                    results[idx] = res.replace('__NL__', '\n')
        except Exception:
            # Fallback on total failure
            for idx, t in batch:
                res = translate_value(google_code, t)
                results[idx] = res.replace('__NL__', '\n')
        return len(batch)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(translate_batch_worker, b) for b in batches]
        for fut in concurrent.futures.as_completed(futures):
            done_count += fut.result()
            if progress_cb:
                progress_cb(done_count)

    return results
