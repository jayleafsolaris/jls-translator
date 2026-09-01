from ..common import state
from ..common.cache import load_cache, save_cache
from ..common.lang_io import parse_lang, write_lang, entries_dict
from ..common.progress import load_base, base_fingerprint, load_progress, save_progress, clear_progress, format_duration, _report_keys, _ask_continue
from ..common.state import DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER
import time


def cmd_remove(resume=False, interactive=False, show_summary=False):
    base_lines = load_base()
    base_values = entries_dict(base_lines)

    existing_codes = [code for code in LANGUAGES if (state.SCRIPT_DIR / f"{code}.lang").exists()]
    if not existing_codes:
        print("No .lang files to clean up. Run --create or --add first.")
        return

    fingerprint = base_fingerprint(base_values)
    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "remove":
            print("No interrupted --remove run found. Starting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            print(f"Resuming --remove: {len(completed)}/{len(existing_codes)} language(s) already checked (accumulated time: {format_duration(elapsed_time)}).\n")

    # Pre-calculate totals for the progress bar
    total_keys_to_check = 0
    keys_checked = 0
    for code in existing_codes:
        count = sum(1 for l in parse_lang(state.SCRIPT_DIR / f"{code}.lang") if l[0] == "entry")
        total_keys_to_check += count
        if code in completed:
            keys_checked += count

    print(f"Removing deprecated keys...\n")
    start_run_time = time.time()
    summary = []
    total_removed = 0

    for lang_idx, code in enumerate(existing_codes, start=1):
        if code in completed:
            continue

        target_path = state.SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)

        removed_this_lang = 0
        out_lines = []

        for line in target_lines:
            if line[0] != "entry":
                out_lines.append(line)
                continue

            keys_checked += 1
            _report_keys("Checking", min(keys_checked, total_keys_to_check), total_keys_to_check)

            _, key, value, inline_comment = line

            if key not in base_values:
                removed_this_lang += 1
                continue

            out_lines.append(line)

        write_lang(target_path, out_lines)
        summary.append((code, removed_this_lang))
        total_removed += removed_this_lang

        completed.append(code)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("remove", completed, fingerprint, current_total_time)

        if interactive and lang_idx < len(existing_codes) and not _ask_continue(code):
            print(f"\nStopped after {code} ({len(completed)}/{len(existing_codes)} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()

    cache = load_cache()
    trimmed_cache = {k: v for k, v in cache.items() if k in base_values or k == _UPDATE_COUNT_MARKER}
    if trimmed_cache != cache:
        save_cache(trimmed_cache)

    if total_removed == 0:
        print(f"\n\nNo deprecated keys found — all present .lang files already match {DEFAULTS['base_lang']}'s keys (took {format_duration(total_duration)}).")
    else:
        print(f"\n\nCleanup complete in {format_duration(total_duration)}:")
        if show_summary:
            for code, removed in summary:
                print(f"  {code}.lang: {removed} key(s) removed")
        else:
            print(f"  Removed {total_removed} total key(s) across {len(summary)} language(s).")
