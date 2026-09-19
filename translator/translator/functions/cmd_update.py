from ..common import state
from ..common.cache import (
    load_cache, save_cache, get_update_count, write_update_count, write_languages_json,
    get_active_language_codes, resolve_workers,
)
from ..common.config_store import warn_red
from ..common.lang_io import parse_lang, write_lang, entries_dict, translator_reference_keys, strip_translator_references
from ..common.netcheck import require_internet_or_warn
from ..common.progress import load_base, sync_en_us_from_base, base_fingerprint, clear_progress, load_progress, save_progress, format_duration, SmoothProgress, _confirm_overwrite_saved_task
from ..common.ratelimit import set_job_profile, status_report
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT, PACKAGE_DIR
from ..common.text_protect import tokens_only_diff, punctuation_only_diff, to_british
from ..common.translate import translate_many, reset_outage_state
import json
import random
import sys
import time
from ..modes.update import CLR_DARK_GREEN, CLR_DIM, CLR_ORANGE, CLR_PINK, CLR_RED, CLR_RESET, MAX_SLOW_LEVEL, USAGE_EASE_FACTOR
from ._quiet_warnings import _quiet_warnings
from ._slow_delay import _slow_delay


def cmd_update(resume=False, interactive=False, show_summary=False):
    base_lines = load_base()
    start_run_time = time.time()

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

    if not resume:
        saved = load_progress()
        if saved and not _confirm_overwrite_saved_task("update", saved.get("command", "an interrupted")):
            print("Cancelled. Run --continue to resume the saved task instead.")
            return

    ref_keys = translator_reference_keys(base_lines)

    # Keys whose base text changed by ONLY a token (a number, placeholder,
    # etc.) since the last cache save -- these are deferred to --apply's
    # lightweight local patch (see functions/cmd_apply.py) instead of
    # being sent to Google Translate at all. Computed once, since it
    # depends only on base's own before/after text, not on any one
    # language. Excluded from the cache update at the end of this run too
    # (see save_cache calls below), so --apply can still detect and patch
    # them later using the same before/after comparison.
    token_only_changed_keys = {
        key for key, value in base_values.items()
        if key in cache and cache[key] != value and tokens_only_diff(cache[key], value) is not None
    }

    # Same idea, but for a base change limited to leading/trailing
    # punctuation (a "!" added, a "." swapped for a "?", and so on) --
    # deferred to --apply's lightweight local patch too, instead of being
    # sent to Google Translate. Checked only for keys tokens_only_diff
    # didn't already claim above, since a key can't be deferred twice.
    punct_only_changed_keys = {
        key for key, value in base_values.items()
        if key in cache and cache[key] != value and key not in token_only_changed_keys
        and punctuation_only_diff(cache[key], value) is not None
    }

    def build_new_cache():
        # Starts from the CURRENT cache (so deferred keys keep their old,
        # stale value) and only advances the keys that were actually
        # accounted for this run -- everything except what got deferred
        # to --apply above.
        new_cache = dict(cache)
        for key, value in base_values.items():
            if key not in token_only_changed_keys and key not in punct_only_changed_keys:
                new_cache[key] = value
        return new_cache

    active_codes = set(get_active_language_codes())
    all_existing_codes = [
        code for code in LANGUAGES
        if code in active_codes and (state.SCRIPT_DIR / f"{code}.lang").exists()
    ]
    # en_US is fully handled above by sync_en_us_from_base() -- a complete
    # rewrite from base every run, already resolved and stripped -- so it
    # never goes through this command's own incremental diff/translate
    # logic below. Letting it through there too was actively harmful:
    # this loop's own "changed_in_base" check would queue a local re-copy
    # of base's RAW, unresolved text for en_US whenever cache was out of
    # sync with base (which is the common case), silently undoing what
    # sync_en_us_from_base had just written only lines earlier in the
    # very same run.
    existing_codes = [code for code in all_existing_codes if code != "en_US"]
    if not existing_codes:
        if "en_US" in all_existing_codes:
            print("\nen_US.lang refreshed from base. No other active .lang files to update.")
        else:
            print("No active .lang files to update. Run --create or --add first, "
                  "or check --config --languages if you expected some here.")
        return

    lang_data = {}
    tasks = []
    for code in existing_codes:
        google_code = LANGUAGES[code]
        target_path = state.SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)
        entries = [line for line in target_lines if line[0] == "entry"]

        to_update = []

        for i, (_, key, current_value, inline_comment) in enumerate(entries):
            if key not in base_values or key in ref_keys:
                continue

            changed_in_base = key in cache and cache[key] != base_values[key]
            needs_fill = google_code is not None and current_value.strip() == ""

            if not (changed_in_base or needs_fill):
                continue

            if changed_in_base and not needs_fill and (
                key in token_only_changed_keys or key in punct_only_changed_keys
            ):
                continue

            to_update.append(i)

        lang_data[code] = {
            "target_path": target_path,
            "target_lines": target_lines,
            "entries": entries,
            "to_update": to_update,
        }
        for i in to_update:
            tasks.append({"code": code, "key": entries[i][1], "google_code": google_code})

    total = len(tasks)
    if total == 0:
        clear_progress()
        save_cache(build_new_cache())
        print(f"\nNo keys needed updating — all present .lang files already match {DEFAULTS['base_lang']}.")
        return

    real_tasks = [t for t in tasks if t["google_code"] not in (None, GB_CONVERT)]
    estimated_bytes = sum(len(base_values[t["key"]].encode("utf-8")) for t in real_tasks)
    set_job_profile(len(real_tasks), estimated_bytes)

    results = {}
    total_duration = 0.0
    suppressed_errors = []

    if total:
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
        _last_line_count = 4
        _slow_level_display = 0
        _shown_hour_pct = None
        _shown_day_pct = None

        def _render(done, _total=total):
            nonlocal _first_render, _last_line_count, _shown_hour_pct, _shown_day_pct

            pct = (done / _total * 100) if _total else 100.0
            time_str = format_duration(time.time() - start_run_time)
            usage = status_report()

            if _shown_hour_pct is None:
                _shown_hour_pct = usage["hour_pct"]
                _shown_day_pct = usage["day_pct"]
            else:
                _shown_hour_pct += (usage["hour_pct"] - _shown_hour_pct) * USAGE_EASE_FACTOR
                _shown_day_pct += (usage["day_pct"] - _shown_day_pct) * USAGE_EASE_FACTOR

            progress_line = f"\033[K  Progress: {pct:5.1f}%"
            if _slow_level_display:
                if _slow_level_display <= 3:
                    slow_color = CLR_PINK
                elif _slow_level_display <= 7:
                    slow_color = CLR_ORANGE
                else:
                    slow_color = CLR_RED
                progress_line += f" {slow_color}(Slowed {_slow_level_display}/{MAX_SLOW_LEVEL}){CLR_RESET}"

            lines = [
                f"\033[K  Translating {_total} keys...",
                progress_line,
                f"\033[K  Time: {time_str}",
                f"\033[K  Usage: Hourly {_shown_hour_pct:.1f}% • Daily {_shown_day_pct:.1f}%",
            ]

            cursor_up = "" if _first_render else f"\033[{_last_line_count}F"
            _first_render = False
            _last_line_count = len(lines)

            sys.stdout.write(cursor_up + "\n".join(lines) + "\n")
            sys.stdout.flush()

        fatal_error_count = 0

        try:
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

            by_google_code = {}
            for t in remaining:
                if t["google_code"] in (None, GB_CONVERT):
                    continue
                by_google_code.setdefault(t["google_code"], []).append(t)

            slow_level = 0

            for google_code, group in by_google_code.items():
                texts = [base_values[t["key"]] for t in group]
                base_offset = done_count

                def _progress_cb(group_done, _base_offset=base_offset):
                    smoother.update(_base_offset + group_done)

                workers = resolve_workers(len(texts))

                while True:
                    suppressed = []
                    try:
                        with _quiet_warnings(suppressed):
                            translated = translate_many(google_code, texts, workers, progress_cb=_progress_cb)
                    except Exception:
                        # SystemExit is deliberately NOT caught here.
                        # translate_many() raises it (via
                        # _handle_rate_limit_stop / a detected outage)
                        # specifically to mean "stop now, progress is
                        # already saved, resume with --continue" -- not
                        # "retry me." Catching it here used to silently
                        # absorb that into up to MAX_SLOW_LEVEL retries,
                        # each one immediately re-hitting the same daily
                        # cap and re-printing the same warning (which
                        # itself bypassed _quiet_warnings -- see that
                        # file), climbing "(Slowed x/15)" while
                        # corrupting this progress display instead of
                        # actually stopping.
                        slow_level += 1
                        if slow_level > MAX_SLOW_LEVEL:
                            for msg in suppressed:
                                warn_red(msg)
                            raise
                        _slow_level_display = slow_level
                        reset_outage_state()
                        time.sleep(_slow_delay(slow_level))
                        continue

                    if slow_level > 0:
                        slow_level -= 1
                    _slow_level_display = slow_level
                    break

                for t, value in zip(group, translated):
                    results[task_key(t["code"], t["key"])] = value
                done_count = base_offset + len(group)
                smoother.update(done_count)
                save_temp()
                save_progress("update", [], fingerprint, time.time() - start_run_time)

                remaining_bytes = sum(
                    len(base_values[t["key"]].encode("utf-8"))
                    for grp in by_google_code.values() for t in grp
                    if task_key(t["code"], t["key"]) not in results
                )
                remaining_keys = sum(
                    1 for grp in by_google_code.values() for t in grp
                    if task_key(t["code"], t["key"]) not in results
                )
                set_job_profile(remaining_keys, remaining_bytes)

            smoother.finish()
        except Exception as err:
            # SystemExit is deliberately not caught here either -- see
            # the matching note on the inner retry loop above. A
            # deliberate stop already printed its own clear explanation;
            # dressing it up as a "Fatal Exception" on top of that would
            # just be confusing.
            fatal_error_count += 1
            time_str = format_duration(time.time() - start_run_time)
            usage = status_report()

            cursor_up = "" if _first_render else "\033[4F"
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

        if temp_path.exists():
            temp_path.unlink()

    total_duration = time.time() - start_run_time
    clear_progress()
    save_cache(build_new_cache())
    write_languages_json()

    summary = []
    for code in existing_codes:
        data = lang_data[code]
        entries = data["entries"]
        changed = 0
        for i in data["to_update"]:
            _, key, _, inline_comment = entries[i]
            value = results.get(task_key(code, key)) if total else None
            if value is None:
                continue
            entries[i] = ("entry", key, value, inline_comment)
            changed += 1

        out_lines = []
        e_idx = 0
        for line in data["target_lines"]:
            if line[0] != "entry":
                out_lines.append(line)
            else:
                out_lines.append(entries[e_idx])
                e_idx += 1
        out_lines = strip_translator_references(out_lines, ref_keys)
        write_lang(data["target_path"], out_lines)
        summary.append((code, changed))

    new_update_count = update_count + 1
    write_update_count(new_update_count)

    if show_summary:
        print(f"\n\nUpdate complete in {format_duration(total_duration)}:")
        for code, changed in summary:
            print(f"  {code}.lang: {changed} key(s) updated")
    else:
        total_updated = sum(changed for _, changed in summary)
        each = total_updated // len(summary) if summary else 0
        print(f"\n\nUpdated {total_updated} key(s) across {len(summary)} language(s) "
              f"({each} each) in {format_duration(total_duration)}.")

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

    if suppressed_errors:
        print(f"\n{CLR_RED}Suppressed Non-Fatal Errors ({len(suppressed_errors)}):{CLR_RESET}")
        for idx, err in enumerate(suppressed_errors, 1):
            print(f"  {idx}. {type(err).__name__}: {err}")
