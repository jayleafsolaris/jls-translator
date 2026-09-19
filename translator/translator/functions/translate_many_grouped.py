from ..common import debug_log
from ..common.ratelimit import RateLimitExceededError
from ..common.text_protect import split_segments, join_segments
import concurrent.futures
import sys
import threading
from ..common.translate import TranslationUnavailableError
from ._handle_rate_limit_stop import _handle_rate_limit_stop
from ._raw_translate_once import _raw_translate_once
from ._record_success import _record_success
from ._translate_segments_deferred import _translate_segments_deferred


def translate_many_grouped(jobs, max_workers, progress_cb=None, on_job_done=None):
    """
    Like translate_many(), but for several (job_key, google_code, texts)
    jobs at once, sharing ONE pool of `max_workers` threads across every
    job instead of giving each language its own separate pool and running
    languages one at a time to completion.

    cmd_update.py used to do `for google_code, group in
    by_google_code.items(): translate_many(...)`, fully finishing one
    language before even submitting a request for the next. Each
    language's pool was sized off *that language's own* task count alone,
    so a run queued behind several smaller languages spent most of its
    wall-clock time with only a handful of workers doing anything, while
    every other language's work sat completely idle waiting its turn --
    even though the thing that actually paces requests (see
    common/ratelimit.py's reserve()) is a single global budget shared by
    everything regardless of how the work is grouped on this end, so
    serializing languages wasn't protecting anything. Submitting every
    language's batches into one shared pool lets one language's network
    round-trip overlap with another's instead of leaving workers idle,
    without sending any more bytes or requests than doing them one at a
    time would have -- reserve()'s pacing still governs how fast anything
    actually goes out, exactly as before.

    `jobs` is a list of (job_key, google_code, texts) tuples. job_key is
    any hashable the caller uses to identify the job afterwards (the
    google_code itself works fine when each job already has a unique one).

    `on_job_done(job_key, job_results)`, if given, fires as soon as every
    value in that one job has resolved -- independently of whether other
    jobs are still running -- so a caller can persist/save progress
    per-language exactly as translate_many() being called once per
    language used to allow, just without waiting for languages to run in
    sequence to get that granularity.

    Returns {job_key: [translated_text, ...]} (same order as that job's
    own input texts), same as calling translate_many() once per job would
    have, once everything finishes.
    """
    debug_log.log(f"translate_many_grouped start -- {len(jobs)} jobs, {max_workers} workers")

    results = {}
    value_parts = {}
    value_remaining = {}
    job_pending = {}
    job_done_fired = set()
    segment_to_values = {}
    segment_results = {}
    all_batches = []

    MAX_BATCH_CHARS = 2500
    MIN_BATCH_FLOOR = 8

    remaining_lock = threading.Lock()

    def _maybe_finish_job(job_key):
        """Must be called with remaining_lock held. Rebuilds and fires
        on_job_done for job_key the moment nothing in it is still
        pending -- possibly immediately, for a job with no real
        translation work in it at all (blank/token-only values only)."""
        if job_pending.get(job_key, 0) > 0 or job_key in job_done_fired:
            return
        job_done_fired.add(job_key)
        job_results = results[job_key]
        for idx in range(len(job_results)):
            if job_results[idx] is not None:
                continue
            parts = value_parts.get((job_key, idx))
            if parts is None:
                continue
            rebuilt = []
            for kind, content in parts:
                if kind == "token":
                    rebuilt.append(content)
                else:
                    rebuilt.append(segment_results.get((job_key, content), content))
            job_results[idx] = "".join(rebuilt).replace('__NL__', '\n')
        if on_job_done:
            on_job_done(job_key, job_results)

    for job_key, google_code, texts in jobs:
        job_results = [None] * len(texts)
        results[job_key] = job_results

        valid_indices = [i for i, t in enumerate(texts) if t.strip()]
        for i in range(len(texts)):
            if not texts[i].strip():
                job_results[i] = texts[i]

        job_segment_order = []
        pending_for_job = 0
        for idx in valid_indices:
            text_clean = texts[idx].replace('\n', '__NL__')
            parts = split_segments(text_clean)
            value_parts[(job_key, idx)] = parts
            distinct_text = {content for kind, content in parts if kind == "text"}
            if not distinct_text:
                job_results[idx] = join_segments(parts).replace('__NL__', '\n')
                continue
            value_remaining[(job_key, idx)] = len(distinct_text)
            pending_for_job += 1
            for content in distinct_text:
                key = (job_key, content)
                if key not in segment_to_values:
                    segment_to_values[key] = set()
                    job_segment_order.append(content)
                segment_to_values[key].add(idx)
        job_pending[job_key] = pending_for_job

        if job_segment_order:
            desired_min_batches = min(len(job_segment_order), MIN_BATCH_FLOOR)
            target_batch_count = min(len(job_segment_order), max(max_workers, desired_min_batches))
            items_per_batch = max(1, -(-len(job_segment_order) // target_batch_count))

            current_batch = []
            current_len = 0
            for seg in job_segment_order:
                if current_batch and (
                    current_len + len(seg) > MAX_BATCH_CHARS
                    or len(current_batch) >= items_per_batch
                ):
                    all_batches.append((job_key, google_code, current_batch))
                    current_batch = []
                    current_len = 0
                current_batch.append(seg)
                current_len += len(seg) + 1
            if current_batch:
                all_batches.append((job_key, google_code, current_batch))

    done_count = sum(
        1 for job_key, _, texts in jobs for idx in range(len(texts))
        if (job_key, idx) not in value_remaining
    )
    with remaining_lock:
        for job_key, _, _ in jobs:
            _maybe_finish_job(job_key)

    def resolve_segment(job_key, seg, translated):
        segment_results[(job_key, seg)] = translated
        newly_done = 0
        with remaining_lock:
            for idx in segment_to_values[(job_key, seg)]:
                value_remaining[(job_key, idx)] -= 1
                if value_remaining[(job_key, idx)] == 0:
                    newly_done += 1
                    job_pending[job_key] -= 1
            _maybe_finish_job(job_key)
        return newly_done

    def translate_batch_worker(job_key, google_code, batch):
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
                completed_values += resolve_segment(job_key, seg, translated_map[seg])
            return completed_values

        lines = [line.replace('\r', '') for line in translated.split('\n')]
        completed_values = 0
        if len(lines) == len(batch):
            for i, seg in enumerate(batch):
                completed_values += resolve_segment(job_key, seg, lines[i])
        else:
            translated_map = _translate_segments_deferred(google_code, batch)
            for seg in batch:
                completed_values += resolve_segment(job_key, seg, translated_map[seg])
        return completed_values

    if all_batches:
        debug_log.log(f"submitting {len(all_batches)} batches across {len(jobs)} jobs (shared pool)")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(translate_batch_worker, jk, gc, b) for jk, gc, b in all_batches]
            try:
                for fut in concurrent.futures.as_completed(futures):
                    done_count += fut.result()
                    debug_log.log(f"batch done -- {done_count} values resolved (all jobs)")
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

    return results
