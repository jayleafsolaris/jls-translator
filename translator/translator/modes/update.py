"""--update: retranslate changed keys already present in each .lang file."""

import json
import sys
import time
import traceback

from ..common import state
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT, PACKAGE_DIR
from ..common.lang_io import parse_lang, write_lang, entries_dict
from ..common.text_protect import tokens_only_diff, apply_token_patch, to_british
from ..common.netcheck import require_internet_or_warn
from ..common.config_store import warn_red
from ..common.translate import translate_many
from ..common.cache import load_cache, save_cache, get_update_count, write_update_count, get_active_language_codes, resolve_workers
from ..common.progress import (
    load_base, sync_en_us_from_base, base_fingerprint, clear_progress, save_progress,
    format_duration, SmoothProgress, _report_keys,
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
            _usage = 0

            cursor_up = "" if _first_render else "\033[4F"
            _first_render = False

            lines = [
                f"\033[K  Translating {_total} keys...",
                f"\033[K  Progress: {pct:5.1f}%",
                f"\033[K  Time: {time_str}",
                f"\033[K  Usage: {_usage}%",
            ]

            sys.stdout.write(cursor_up + "\n".join(lines) + "\n")
            sys.stdout.flush()

        smoother = SmoothProgress(total, _render)
        fatal_error_count = 0
        
        try:
            smoother.update(done_count)

            # Local (non-network) work first: direct copy (en_US) and British-spelling
            # conversion (en_GB) need no API call at all.
            for t in [t for t in remaining if t["google_code"] in (None, GB_CONVERT)]:
                text = base_values[t["key"]]
                value = text if t["google_code"] is None else to_british(text)
                results[task_key(t["code"], t["key"])] = value
                done_count += 1
                smoother.update(done_count)
            save_temp()
            save_progress("update", [], fingerprint, time.time() - start_run_time)

            # Real network translation, grouped by target Google language code (one
            # 'es' batch covers both es_ES and es_MX, for example) but reported as a
            # single running total across every language.
            by_google = {}
            for t in remaining:
                if t["google_code"] in (None, GB_CONVERT):
                    continue
                by_google.setdefault(t["google_code"], []).append(t)

            for google_code, group in by_google.items():
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

            smoother.finish()
        except Exception as err:
            fatal_error_count += 1
            time_str = format_duration(time.time() - start_run_time)
            _usage = 0

            # Render fatal output layout over current display block
            cursor_up = "" if _first_render else "\033[4F"
            fatal_lines = [
                f"\033[K  Translating {total} keys - Fatal Exception",
                f"\033[K  Progress: 0% (Failed)",
                f"\033[K  Time: {time_str}",
                f"\033[K  Usage: {_usage}% (Not impacted by failure)",
                f"\033[K  {CLR_RED}Fatal Errors: {fatal_error_count}{CLR_RESET}",
                f"\033[K  {CLR_DARK_GREEN}Please try again in 0 minutes{CLR_RESET}",
            ]
            sys.stdout.write(cursor_up + "\n".join(fatal_lines) + "\n")
            sys.stdout.flush()
            raise err

        total_duration = time.time() - start_run_time
        if temp_path.exists():
            temp_path.unlink()

    clear_progress()
    save_cache(base_values)

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
    print(f"\nHourly Usage: 0% - Resets in N/A")
    print(f"\nDaily Usage: 0% - Resets in N/A")
    print(f"Cooldown: 1 hour - Ready at ??:??")
    print(f"You have reached the <usage_type> usage limit to prevent a temporary IP limit/ban")

    # Display any non-fatal suppressed errors cleanly at the end of output
    if suppressed_errors:
        print(f"\n{CLR_RED}Suppressed Non-Fatal Errors ({len(suppressed_errors)}):{CLR_RESET}")
        for idx, err in enumerate(suppressed_errors, 1):
            print(f"  {idx}. {type(err).__name__}: {err}")