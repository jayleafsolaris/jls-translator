"""--add: only add missing keys (no change detection, no network calls)."""

import time

from ..common import state
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT
from ..common.lang_io import parse_lang, write_lang, entries_dict, strip_comments_for_output
from ..common.text_protect import to_british
from ..common.cache import get_active_language_codes, write_languages_json
from ..common.progress import (
    load_base, sync_en_us_from_base, base_fingerprint, load_progress,
    save_progress, clear_progress, format_duration, _report_keys, _ask_continue,
)

def cmd_add(resume=False, interactive=False, show_summary=False):
    # --add never calls Google Translate -- missing keys are filled in with a
    # direct copy (en_US), a British-spelling conversion (en_GB), or left
    # blank as an untranslated placeholder (run --update afterward to fill
    # those in). None of that needs network access.
    base_lines = load_base()
    # Never propagate comments (section headers, notes, disabled entries)
    # or the hidden --update count marker into generated output files --
    # only the source-of-truth base file should carry any of that.
    template_lines = strip_comments_for_output(base_lines)
    sync_en_us_from_base(base_lines)
    base_values = entries_dict(base_lines)
    key_total = len(base_values)
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
        if not progress or progress.get("command") != "add":
            print("No interrupted --add run found.\nStarting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            if progress.get("fingerprint") != fingerprint:
                print(f"Note: {DEFAULTS['base_lang']} has changed since that run was interrupted — "
                      "resuming anyway using the languages already completed.\n")
            print(f"Resuming --add: {len(completed)}/{lang_total} language(s) already done (accumulated time: {format_duration(elapsed_time)}).\n")

    total_keys_to_check = lang_total * key_total
    keys_checked = len(completed) * key_total

    print(f"Adding missing keys...\n")
    start_run_time = time.time()
    summary = []
    total_added_overall = 0

    for lang_idx, (code, google_code) in enumerate(all_codes, start=1):
        if code in completed:
            continue

        target_path = state.SCRIPT_DIR / f"{code}.lang"
        existing = entries_dict(parse_lang(target_path))

        entries = []
        added_this_lang = 0

        for line in template_lines:
            if line[0] != "entry":
                continue

            keys_checked += 1
            _report_keys("Checking", keys_checked, total_keys_to_check)

            _, key, value, inline_comment = line
            if key in existing:
                entries.append(("entry", key, existing[key], inline_comment))
            else:
                if google_code is None:
                    placeholder = value
                elif google_code == GB_CONVERT:
                    placeholder = to_british(value)
                else:
                    placeholder = ""
                entries.append(("entry", key, placeholder, inline_comment))
                added_this_lang += 1

        total_added_overall += added_this_lang

        out_lines = []
        e_idx = 0
        for line in template_lines:
            if line[0] != "entry":
                out_lines.append(line)
            else:
                out_lines.append(entries[e_idx])
                e_idx += 1

        write_lang(target_path, out_lines)
        summary.append((code, added_this_lang))

        completed.append(code)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("add", completed, fingerprint, current_total_time)

        if interactive and lang_idx < lang_total and not _ask_continue(code):
            write_languages_json()
            print(f"\nStopped after {code} ({len(completed)}/{lang_total} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()
    write_languages_json()

    print(f"\n\nAdd complete in {format_duration(total_duration)}:")
    if show_summary:
        for code, added in summary:
            print(f"  {code}.lang: {added} new key(s) added (untranslated -- run --update to translate)")
    else:
        print(f"  Added {total_added_overall} total missing key(s) across {len(summary)} language(s).")
