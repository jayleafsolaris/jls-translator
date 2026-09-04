from ..common import state
from ..common.cache import (
    get_active_language_codes, save_cache, write_languages_json, write_update_count, resolve_workers,
    load_translator_reference_cache, save_translator_reference_cache,
)
from ..common.lang_io import strip_comments_for_output, entries_dict, write_lang, translator_reference_keys, strip_translator_references
from ..common.netcheck import require_internet_or_warn
from ..common.progress import load_base, sync_en_us_from_base, base_fingerprint, load_progress, save_progress, clear_progress, format_duration, _report, SmoothProgress, _ask_continue
from ..common.ratelimit import set_job_profile, status_report
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT
from ..common.text_protect import to_british, resolve_key_references
from ..common.translate import translate_many
import time


def cmd_create(resume=False, interactive=False):
    if not require_internet_or_warn("--create"):
        return
    base_lines = load_base()
    # Never propagate comments (section headers, notes, disabled entries)
    # or the hidden --update count marker into generated output files --
    # only the source-of-truth base file should carry any of that.
    template_lines = strip_comments_for_output(base_lines)
    sync_en_us_from_base(base_lines)
    base_values = entries_dict(base_lines)
    key_total = len(base_values)
    ref_keys = translator_reference_keys(base_lines)
    translator_ref_cache = load_translator_reference_cache()
    active_codes = get_active_language_codes()
    if not active_codes:
        print("No active languages configured. Run --config --languages to activate some first.")
        return
    all_codes = [(code, LANGUAGES[code]) for code in active_codes]
    lang_total = len(all_codes)
    fingerprint = base_fingerprint(base_values)

    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "create":
             print("No interrupted --create run found. Starting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            if progress.get("fingerprint") != fingerprint:
                print(f"Note: {DEFAULTS['base_lang']} has changed since that run was interrupted — "
                      "resuming anyway using the languages already completed.\n")
            print(f"Resuming --create: {len(completed)}/{lang_total} language(s) already done (accumulated time: {format_duration(elapsed_time)}).\n")

    # Feed the rate limiter a rough estimate of how much real (networked)
    # translation work is left, across every language not yet completed,
    # so its adaptive cooldown can pace itself sensibly from the start
    # instead of only reacting after the first hourly/daily cap is hit.
    remaining_real_codes = [
        (code, gc) for code, gc in all_codes
        if code not in completed and gc not in (None, GB_CONVERT)
    ]
    estimated_bytes = sum(len(v.encode("utf-8")) for v in base_values.values()) * len(remaining_real_codes)
    estimated_keys = key_total * len(remaining_real_codes)
    set_job_profile(estimated_keys, estimated_bytes)

    print(f"Translating {key_total} keys into {lang_total} languages...\n")
    start_run_time = time.time()

    for lang_idx, (code, google_code) in enumerate(all_codes, start=1):
        if code in completed:
            continue
        _report(lang_idx, lang_total, code, 0, key_total, start_run_time, elapsed_time)

        if google_code is None:
            out_lines = list(template_lines)

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render, catch_up_seconds=3.0)
            smoother.update(key_total)
            smoother.finish()
        elif google_code == GB_CONVERT:
            out_lines = [
                line if line[0] != "entry" else ("entry", line[1], to_british(line[2]), line[3])
                for line in template_lines
            ]

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render, catch_up_seconds=3.0)
            smoother.update(key_total)
            smoother.finish()
        else:
            values = [line[2] for line in template_lines if line[0] == "entry"]

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render)
            effective_workers = resolve_workers(len(values))
            translated = translate_many(google_code, values, effective_workers, progress_cb=smoother.update)
            smoother.finish()

            out_lines = []
            t_idx = 0
            for line in template_lines:
                if line[0] != "entry":
                    out_lines.append(line)
                    continue
                _, key, _, inline_comment = line
                out_lines.append(("entry", key, translated[t_idx], inline_comment))
                t_idx += 1

        # Resolve any '{key.path}' cross-references now that this
        # language's entries are fully generated (see
        # common/text_protect.py's resolve_key_references()) -- mirrors
        # --update's post-translation resolution phase, so freshly
        # --create'd files don't leave a raw '{key.path}' marker behind
        # either. Resolved within this language's own entries only.
        current_values = {line[1]: line[2] for line in out_lines if line[0] == "entry"}
        resolved_values = resolve_key_references(current_values)
        out_lines = [
            line if line[0] != "entry" or resolved_values.get(line[1], line[2]) == line[2]
            else ("entry", line[1], resolved_values[line[1]], line[3])
            for line in out_lines
        ]

        # Translator Reference entries (see translator_reference_keys())
        # were translated above like any other key -- needed so the
        # '{key.path}' resolution just above can splice their translated
        # text into whatever else references them -- but they're never
        # meant to be a key of their own in the actual .lang file. Stash
        # their now-translated values in the persisted cache (so a later
        # --update can detect drift/resolve references without
        # retranslating them from scratch) before dropping them from what
        # actually gets written.
        if ref_keys:
            lang_ref_cache = translator_ref_cache.setdefault(code, {})
            for key in ref_keys:
                if key in resolved_values:
                    lang_ref_cache[key] = resolved_values[key]
            out_lines = strip_translator_references(out_lines, ref_keys)

        write_lang(state.SCRIPT_DIR / f"{code}.lang", out_lines)

        completed.append(code)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("create", completed, fingerprint, current_total_time)

        # Refresh the job profile as languages finish, so the cooldown
        # reflects what's actually left rather than the original estimate
        # from the top of the run.
        remaining_real_codes = [
            (c, gc) for c, gc in all_codes
            if c not in completed and gc not in (None, GB_CONVERT)
        ]
        set_job_profile(
            key_total * len(remaining_real_codes),
            sum(len(v.encode("utf-8")) for v in base_values.values()) * len(remaining_real_codes),
        )

        if interactive and lang_idx < lang_total and not _ask_continue(code):
            save_cache(base_values)
            write_languages_json()
            if ref_keys:
                save_translator_reference_cache(translator_ref_cache)
            print(f"\nStopped after {code} ({len(completed)}/{lang_total} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()
    save_cache(base_values)
    write_languages_json()
    if ref_keys:
        # Drop any cached translations for keys that no longer exist in
        # base or have moved out of the Translator References section --
        # otherwise a removed/renamed reference's stale text would sit
        # around forever with nothing left to ever overwrite it.
        for code in list(translator_ref_cache):
            translator_ref_cache[code] = {
                k: v for k, v in translator_ref_cache[code].items() if k in ref_keys
            }
        save_translator_reference_cache(translator_ref_cache)
    # A full --create fully regenerates everything from base, so this is
    # the reset point for the --update run counter.
    write_update_count(0)
    print(f"\nDone. Created {lang_total} language files from {DEFAULTS['base_lang']} in {format_duration(total_duration)}.")

    report = status_report(use_cache=False)
    print(f"\nHourly Usage: {report['hour_pct']:.0f}% - Resets in {report['hour_reset_str']}")
    print(f"Daily Usage: {report['day_pct']:.0f}% - Resets in {report['day_reset_str']}")
