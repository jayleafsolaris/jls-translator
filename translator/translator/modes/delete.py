"""--delete: delete every generated .lang file (base is kept)."""

import sys
import time

from ..common import state
from ..common.state import DEFAULTS
from ..common.progress import load_progress, save_progress, clear_progress, format_duration, _ask_continue

def cmd_delete(resume=False, interactive=False):
    targets = [
        p for p in state.SCRIPT_DIR.glob("*.lang")
        if p.name != DEFAULTS["base_lang"]
    ]

    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "delete":
            print("No interrupted --delete run found.\nStarting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            print(f"Resuming --delete: {len(completed)} file(s) already deleted (accumulated time: {format_duration(elapsed_time)}).\n")

    targets_to_delete = [p for p in targets if p.name not in completed]

    if not targets_to_delete and not resume:
        print("No translated .lang files to delete.")
        return

    if not resume:
        print(f"This will delete {len(targets_to_delete)} file(s):")
        for p in targets_to_delete:
            print(f"  {p.name}")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

    start_run_time = time.time()
    for lang_idx, p in enumerate(targets_to_delete, start=1):
        if p.exists():
            p.unlink()
        
        completed.append(p.name)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("delete", completed, "none", current_total_time)

        sys.stdout.write(f"\rDeleted {p.name}... time: {format_duration(current_total_time)}".ljust(85))
        sys.stdout.flush()

        if interactive and lang_idx < len(targets_to_delete) and not _ask_continue(p.name):
            print(f"\nStopped after {p.name} ({len(completed)} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()
    print(f"\nDeleted {len(completed)} .lang file(s) in {format_duration(total_duration)}. "
          f"The base file ('{DEFAULTS['base_lang']}') was untouched.")
