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

    valid_indices = [i for i, t in enumerate(texts) if t.strip()]
    for i in range(len(texts)):
        if not texts[i].strip():
            results[i] = texts[i]

    if not valid_indices:
        if progress_cb:
            progress_cb(len(texts))
        return results

    value_parts = {}
    for idx in valid_indices:
        text_clean = texts[idx].replace('\n', '__NL__')
        value_parts[idx] = split_segments(text_clean)

    segment_to_values = {}
    segment_order = []
    value_remaining = {}
    for idx, parts in value_parts.items():
        distinct_text = {content for kind, content in parts if kind == "text"}
        if not distinct_text:
            results[idx] = join_segments(parts).replace('__NL__', '\n')
            continue
        value_remaining[idx] = len(distinct_text)
        for content in distinct_text:
            if content not in segment_to_values:
                segment_to_values[content] = set()
                segment_order.append(content)
            segment_to_values[content].add(idx)

    unique_segments = segment_order
    segment_results = {}

    MAX_BATCH_CHARS = 2500
    batches = []
    current_batch = []
    current_len = 0

    if unique_segments:
        MIN_BATCH_FLOOR = 8
        desired_min_batches = min(len(unique_segments), MIN_BATCH_FLOOR)
        target_batch_count = min(len(unique_segments), max(max_workers, desired_min_batches))
        items_per_batch = max(1, -(-len(unique_segments) // target_batch_count))

        for seg in unique_segments:
            if current_batch and (
                current_len + len(seg) > MAX_BATCH_CHARS
                or len(current_batch) >= items_per_batch
            ):
                batches.append(current_batch)
                current_batch = []
                current_len = 0

            current_batch.append(seg)
            current_len += len(seg) + 1

        if current_batch:
            batches.append(current_batch)

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
        combined = "\n".join(batch)

        try:
            translated = _raw_translate_once(google_code, combined)
            _record_success()
        except TranslationUnavailableError:
            raise
        except RateLimitExceededError:
            raise
        except Exception:
            completed_values = 0
            translated_map = _translate_segments_deferred(google_code, batch)
            for seg in batch:
                completed_values += resolve_segment(seg, translated_map[seg])
            return completed_values

        lines = [line.replace('\r', '') for line in translated.split('\n')]

        completed_values = 0
        if len(lines) == len(batch):
            for i, seg in enumerate(batch):
                completed_values += resolve_segment(seg, lines[i])
        else:
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
                debug_log.log(f"stopping -- {type(err).__name__}: {err}")
                for f in futures:
                    f.cancel()
                ex.shutdown(wait=True, cancel_futures=True)
                if isinstance(err, RateLimitExceededError):
                    _handle_rate_limit_stop(err)
                sys.exit(1)
    elif progress_cb:
        progress_cb(done_count)

    for idx in valid_indices:
        if results[idx] is not None:
            continue
        rebuilt = []
        for kind, content in value_parts[idx]:
            if kind == "token":
                rebuilt.append(content)
            else:
                rebuilt.append(segment_results.get(content, content))
        results[idx] = "".join(rebuilt).replace('__NL__', '\n')

    return results
