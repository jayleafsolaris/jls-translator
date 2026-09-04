from ..common import debug_log
from ..common.ratelimit import reserve, record_extra, record_outage, RateLimitExceededError
from ..common.text_protect import split_segments, join_segments
import concurrent.futures
import sys
import threading
from ..common.translate import TranslationUnavailableError
from ._handle_rate_limit_stop import _handle_rate_limit_stop
from ._raw_translate_once import _raw_translate_once
from ._record_success import _record_success
from ._translate_segments_deferred import _translate_segments_deferred


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
