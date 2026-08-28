"""--update: retranslate changed keys already present in each .lang file."""

import json
import random
import sys
import time
import traceback

from ..common import state
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT, PACKAGE_DIR
from ..common.lang_io import parse_lang, write_lang, entries_dict
from ..common.text_protect import tokens_only_diff, apply_token_patch, to_british, resolve_key_references
from ..common.netcheck import require_internet_or_warn
from ..common.config_store import warn_red
from ..common.translate import translate_many, get_fallback_count
from ..common.ratelimit import set_job_profile, status_report
from ..common.cache import load_cache, save_cache, get_update_count, write_update_count, write_languages_json, get_active_language_codes, resolve_workers
from ..common.progress import (
    load_base, sync_en_us_from_base, base_fingerprint, clear_progress, save_progress,
    format_duration, SmoothProgress, _report_keys, _report_finishing,
)

# ANSI Color Code Constants
CLR_RED = "\033[31m"
CLR_DARK_GREEN = "\033[32m"
CLR_RESET = "\033[0m"


def cmd_update(resume=False, interactive=False):
    base_lines = load_base()

    # Enforce the --update run limit *before* touching the network or
    # doing any work -- once a base file has been --update'd this many
    # times, it needs a full --create to regenerate everything cleanly.
    update_count = get_update_count()
    if update_count >= DEFAULTS["update_limit"]:
        warn_red(
            f"--update limit reached ({update_count}/{DEFAULTS['update_limit']}) for this base file."
        )
        print("This file has reached it's maximum update count. Please create a new set of .lang files to remove any leaked or missed translation keys")
        return

    if not require_internet_or_warn("--update"):
        return
    sync_en_us_from_base(base_lines)
    base_values = entries_dict(base_lines)
    cache = load_cache()
    fingerprint = base_fingerprint(base_values)

    active_codes = set(get_active_language_codes())
    existing_codes = [
        code for code in LANGUAGES
        if code in active_codes and (state.SCRIPT_DIR / f"{code}.lang").exists()
    ]
    if not existing_codes:
        print("No active .lang files to update. Run --create or --add first, "
              "or check --config --languages if you expected some here.")
        return

    # Figure out, for every language at once, exactly which keys need
    # (re)translating. Nothing gets written to a .lang file yet -- that only
    # happens after every translation below is resolved.
    lang_data = {}
    tasks = []
    total_token_patched = 0
    for code in existing_codes:
        google_code = LANGUAGES[code]
        target_path = state.SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)
        entries = [line for line in target_lines if line[0] == "entry"]

        to_update = []
        token_patched_count = 0

        for i, (_, key, current_value, inline_comment) in enumerate(entries):
            if key not in base_values:
                continue

            changed_in_base = key in cache and cache[key] != base_values[key]
            needs_fill = google_code is not None and current_value.strip() == ""

            if not (changed_in_base or needs_fill):
                continue

            # If the base value only changed inside a protected token --
            # a %1$s-style placeholder, a section-sign color code, a PUA
            # glyph -- and every bit of surrounding translatable text is
            # unchanged, there's nothing to retranslate. Just splice the
            # new token(s) into the already-translated string in place and
            # skip Google Translate for this key/language entirely.
            if changed_in_base and not needs_fill and google_code is not None:
                new_tokens = tokens_only_diff(cache[key], base_values[key])
                if new_tokens is not None:
                    patched = apply_token_patch(current_value, new_tokens)
                    if patched is not None:
                        entries[i] = ("entry", key, patched, inline_comment)
                        token_patched_count += 1
                        continue
                    # Token count in the translated string doesn't match the
                    # new base's token count (translator dropped/duplicated
                    # a placeholder, or the .lang was hand-edited) -- fall
                    # through to a full retranslation instead of guessing.

            to_update.append(i)

        lang_data[code] = {
            "target_path": target_path,
            "target_lines": target_lines,
            "entries": entries,
            "to_update": to_update,
            "token_patched_count": token_patched_count,
        }
        total_token_patched += token_patched_count
        for i in to_update:
            tasks.append({"code": code, "key": entries[i][1], "google_code": google_code})

    total = len(tasks)
    if total == 0 and total_token_patched == 0:
        clear_progress()
        save_cache(base_values)
        print(f"\nNo keys needed updating — all present .lang files already match {DEFAULTS['base_lang']}.")
        return

    if total_token_patched:
        print(f"{total_token_patched} key(s) had only token changes "
              f"-- patched in place, no retranslation needed.\n")

    # Feed the rate limiter a rough estimate of how much real (networked)
    # translation work this run represents, so its adaptive cooldown can
    # pace itself sensibly against the remaining hourly/daily budget.
    real_tasks = [t for t in tasks if t["google_code"] not in (None, GB_CONVERT)]
    estimated_bytes = sum(len(base_values[t["key"]].encode("utf-8")) for t in real_tasks)
    set_job_profile(len(real_tasks), estimated_bytes)

    results = {}
    total_duration = 0.0
    suppressed_errors = []

    if total:
        # Hidden scratch file: every finished translation lands here first,
        # keyed by language + key, and is only fanned back out into the real
        # .lang files once the whole combined batch is done. This is also
        # what --continue resumes from if a run gets interrupted.
        temp_path = PACKAGE_DIR / DEFAULTS["update_temp_file"]

        if resume and temp_path.exists():
            try:
                saved = json.loads(temp_path.read_text(encoding="utf-8"))
                if saved.get("fingerprint") == fingerprint:
                    results = saved.get("results", {})
            except Exception as e:
                suppressed_errors.append(e)
                results = {}
        elif temp_path.exists():
            temp_path.unlink()

        def task_key(code, key):
            return f"{code}\x00{key}"

        def save_temp():
            temp_path.write_text(
                json.dumps({"fingerprint": fingerprint, "results": results}, ensure_ascii=False),
                encoding="utf-8",
            )

        remaining = [t for t in tasks if task_key(t["code"], t["key"]) not in results]
        # Shuffle translation order so keys that changed together (often
        # near-identical, similarly-shaped strings sitting adjacent in the
        # base file -- e.g. a batch of blank/templated entries) don't land
        # next to each other in the same or consecutive batches. The
        # failure-streak/outage detector in translate.py trips on N real
        # translation attempts failing back-to-back with no success in
        # between; --create is naturally protected from this by sheer
        # variety, but --update's smaller, more homogeneous key set isn't.
        # Scattering the order gives dissimilar keys a better chance of
        # interleaving between any that are genuinely problematic, instead
        # of stacking them into one unbroken run. Purely cosmetic
        # reordering otherwise -- results are keyed by task, not position,
        # so resuming (--continue) and final output are unaffected.
        random.shuffle(remaining)
        done_count = total - len(remaining)

        if resume:
            if done_count:
                print(f"Resuming --update: {done_count}/{total} translation(s) already completed.\n")
            else:
                print("No interrupted --update run found (or base changed since) -- starting fresh.\n")

        if interactive:
            print("Note: --ask has no effect on --update -- all languages are now "
                  "translated together as a single batch.\n")

        start_run_time = time.time()
        _first_render = True

        def _render(done, _total=total):
            nonlocal _first_render

            pct = (done / _total * 100) if _total else 100.0
            time_str = format_duration(time.time() - start_run_time)
            usage = status_report()  # cached -- cheap to call every tick
            # Non-fatal fallbacks (a value that exhausted its retries and
            # fell back to untranslated text -- see
            # common/translate.py's _translate_segments_deferred) used to
            # print their own "Fatal Errors: N" line mid-run, breaking
            # into the middle of this live block. Folded in here instead,
            # so it's just one more number that updates in place along
            # with everything else.
            fallbacks = get_fallback_count()

            cursor_up = "" if _first_render else "\033[5F"
            _first_render = False

            lines = [
                f"\033[K  Translating {_total} keys...",
                f"\033[K  Progress: {pct:5.1f}%",
                f"\033[K  Time: {time_str}",
                f"\033[K  Usage: Hourly {usage['hour_pct']:.1f}% • Daily {usage['day_pct']:.1f}%",
                f"\033[K  Fallbacks: {fallbacks}" + (f" {CLR_RED}(untranslated, non-fatal){CLR_RESET}" if fallbacks else ""),
            ]

            sys.stdout.write(cursor_up + "\n".join(lines) + "\n")
            sys.stdout.flush()

        fatal_error_count = 0

        try:
            # Local (non-network) work first: direct copy (en_US) and British-spelling
            # conversion (en_GB) need no API call at all. Given its own
            # SmoothProgress scoped just to this local work, with the same
            # 3-second catch-up --create uses for these same two cases --
            # so this instant, no-delay work still visibly eases forward
            # instead of snapping straight to wherever it lands. The main
            # run smoother (below) then takes over for the real, networked
            # translation work.
            local_tasks = [t for t in remaining if t["google_code"] in (None, GB_CONVERT)]
            if local_tasks:
                start_offset = done_count
                local_smoother = SmoothProgress(
                    len(local_tasks),
                    lambda done, _offset=start_offset: _render(_offset + done),
                    catch_up_seconds=3.0,
                )
                for i, t in enumerate(local_tasks, start=1):
                    text = base_values[t["key"]]
                    value = text if t["google_code"] is None else to_british(text)
                    results[task_key(t["code"], t["key"])] = value
                    local_smoother.update(i)
                local_smoother.finish()
                done_count = start_offset + len(local_tasks)
            save_temp()
            save_progress("update", [], fingerprint, time.time() - start_run_time)

            smoother = SmoothProgress(total, _render)
            smoother.update(done_count)

            # Real network translation, one language at a time -- mirrors
            # --create's per-language batching instead of pooling every
            # locale that shares a Google code (e.g. es_ES + es_MX) into a
            # single combined request. Still reported as a single running
            # total across every language.
            by_lang = {}
            for t in remaining:
                if t["google_code"] in (None, GB_CONVERT):
                    continue
                by_lang.setdefault(t["code"], []).append(t)

            for code, group in by_lang.items():
                google_code = group[0]["google_code"]
                texts = [base_values[t["key"]] for t in group]
                base_offset = done_count

                def _progress_cb(group_done, _base_offset=base_offset):
                    smoother.update(_base_offset + group_done)

                workers = resolve_workers(len(texts))
                translated = translate_many(google_code, texts, workers, progress_cb=_progress_cb)
                for t, value in zip(group, translated):
                    results[task_key(t["code"], t["key"])] = value
                done_count = base_offset + len(group)
                smoother.update(done_count)
                save_temp()
                save_progress("update", [], fingerprint, time.time() - start_run_time)

                # Refresh the job profile with what's actually left after
                # this language finishes, so the cooldown reacts to
                # progress rather than just the original estimate.
                remaining_bytes = sum(
                    len(base_values[t["key"]].encode("utf-8"))
                    for grp in by_lang.values() for t in grp
                    if task_key(t["code"], t["key"]) not in results
                )
                remaining_keys = sum(
                    1 for grp in by_lang.values() for t in grp
                    if task_key(t["code"], t["key"]) not in results
                )
                set_job_profile(remaining_keys, remaining_bytes)

            smoother.finish()
        except (Exception, SystemExit) as err:
            # translate.py can end a run two ways: a normal Exception
            # bubbling out of translate_many(), or a direct sys.exit(1)
            # from translate_value()/translate_many() once the failure
            # streak crosses FAILURE_STREAK_THRESHOLD (declared outage) or
            # the daily rate-limit cap is hit. sys.exit() raises SystemExit,
            # which is a BaseException, NOT an Exception -- so it used to
            # skip this handler entirely, silently killing the process
            # with nothing but translate.py's own bare "Fatal Errors: N"
            # line and no context (no progress/usage summary, no re-raised
            # traceback). Catching SystemExit here too means every failure
            # path -- normal exception, outage, or rate limit -- ends up
            # going through the same fatal-error reporting below.
            fatal_error_count += 1
            time_str = format_duration(time.time() - start_run_time)
            usage = status_report()

            # Render fatal output layout over current display block
            cursor_up = "" if _first_render else "\033[5F"
            fatal_lines = [
                f"\033[K  Translating {total} keys - Fatal Exception",
                f"\033[K  Progress: 0% (Failed)",
                f"\033[K  Time: {time_str}",
                f"\033[K  Usage: Hourly {usage['hour_pct']:.1f}% • Daily {usage['day_pct']:.1f}% (not the cause -- see below)",
                f"\033[K  {CLR_RED}Fatal Errors: {fatal_error_count}{CLR_RESET}",
                f"\033[K  {CLR_DARK_GREEN}Please try again in 0 minutes{CLR_RESET}",
            ]
            sys.stdout.write(cursor_up + "\n".join(fatal_lines) + "\033[J\n")
            sys.stdout.flush()
            raise err

        total_duration = time.time() - start_run_time
        if temp_path.exists():
            temp_path.unlink()

    clear_progress()
    save_cache(base_values)
    write_languages_json()

    # Now fan the finished translations back out into each language's .lang
    # file -- this is the only point any .lang file gets touched. Entries
    # that were already token-patched in place above are written out as-is.
    # Reported the same way --add/--remove report their key-by-key sweeps.
    summary = []
    applied = 0
    if total:
        print(f"\n\nApplying {total} translation(s)...\n")
    for code in existing_codes:
        data = lang_data[code]
        entries = data["entries"]
        changed = data["token_patched_count"]
        for i in data["to_update"]:
            _, key, _, inline_comment = entries[i]
            value = results.get(task_key(code, key)) if total else None
            if value is None:
                continue
            entries[i] = ("entry", key, value, inline_comment)
            changed += 1
            applied += 1
            if total:
                _report_keys("Applying", applied, total)

        out_lines = []
        e_idx = 0
        for line in data["target_lines"]:
            if line[0] != "entry":
                out_lines.append(line)
            else:
                out_lines.append(entries[e_idx])
                e_idx += 1
        write_lang(data["target_path"], out_lines)
        summary.append((code, changed, data["token_patched_count"]))

    # Second phase: resolve every '{key.path}' cross-reference (see
    # common/text_protect.py's resolve_key_references()) now that each
    # language's entries reflect this run's final values -- previously
    # these were left as the literal '{key.path}' marker in the output.
    # Runs over every active language regardless of whether it had
    # translations this run, since a lingering unresolved reference could
    # predate this feature.
    print(f"\nFinishing Translations…\n")
    finishing_total = len(existing_codes)
    # Same easing as the main translation bars (SmoothProgress) instead of
    # jumping straight to each language's fraction -- this phase is quick
    # per-language, so an un-smoothed percentage would otherwise leap in
    # big, jarring steps rather than climb.
    finishing_smoother = SmoothProgress(
        finishing_total,
        lambda done, _total=finishing_total: _report_finishing(done, _total),
    )
    for i, code in enumerate(existing_codes, start=1):
        data = lang_data[code]
        entries = data["entries"]
        current_values = {key: val for _, key, val, _ in entries}
        resolved_values = resolve_key_references(current_values)

        changed_refs = False
        for j, (kind, key, val, inline_comment) in enumerate(entries):
            new_val = resolved_values.get(key, val)
            if new_val != val:
                entries[j] = ("entry", key, new_val, inline_comment)
                changed_refs = True

        if changed_refs:
            out_lines = []
            e_idx = 0
            for line in data["target_lines"]:
                if line[0] != "entry":
                    out_lines.append(line)
                else:
                    out_lines.append(entries[e_idx])
                    e_idx += 1
            write_lang(data["target_path"], out_lines)

        finishing_smoother.update(i)
    finishing_smoother.finish()
    print()

    # This --update run did real work (translation and/or token patching),
    # so it counts against the run limit. Persist the incremented count to
    # both base (marker comment) and cache.
    new_update_count = update_count + 1
    write_update_count(new_update_count)

    print(f"\n\nUpdate complete in {format_duration(total_duration)}:")
    for code, changed, patched in summary:
        if patched:
            print(f"  {code}.lang: {changed} key(s) updated ({patched} via token-only patch)")
        else:
            print(f"  {code}.lang: {changed} key(s) updated")

    print(f"\nUpdate count: {new_update_count}/{DEFAULTS['update_limit']}.")
    if new_update_count >= DEFAULTS["update_limit"]:
        warn_red(
            f"--update limit reached ({new_update_count}/{DEFAULTS['update_limit']}) -- "
            f"this base file must be recreated (--create) before --update can run again."
        )

    report = status_report(use_cache=False)
    print(f"\nHourly Usage: {report['hour_pct']:.1f}% - Resets in {report['hour_reset_str']}")
    print(f"Daily Usage: {report['day_pct']:.1f}% - Resets in {report['day_reset_str']}")
    if report["day_pct"] >= 99.0:
        warn_red("Daily usage limit reached -- further translation requests will pause until it resets, "
                  "to avoid a temporary IP rate limit/ban from Google Translate.")
    elif report["hour_pct"] >= 99.0:
        warn_red("Hourly usage limit reached -- further translation requests will pause until it resets, "
                  "to avoid a temporary IP rate limit/ban from Google Translate.")

    # Display any non-fatal suppressed errors cleanly at the end of output
    if suppressed_errors:
        print(f"\n{CLR_RED}Suppressed Non-Fatal Errors ({len(suppressed_errors)}):{CLR_RESET}")
        for idx, err in enumerate(suppressed_errors, 1):
            print(f"  {idx}. {type(err).__name__}: {err}")
