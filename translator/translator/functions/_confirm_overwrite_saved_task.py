def _confirm_overwrite_saved_task(command_name, saved_command):
    """
    Asks the user before a fresh (non---continue) --create/--update run
    would discard an already-saved, interruption-resumable task (see
    load_progress()/save_progress() in this module) -- otherwise starting
    over silently throws away whatever --continue would have picked back
    up, with no warning at all. Defaults to yes (overwrite) on a bare
    Enter, matching this codebase's other y/n prompts (see
    _ask_continue()).

    Returns True to proceed with the fresh run (discarding the saved
    task), False to cancel so the user can run --continue instead.
    """
    while True:
        answer = input(
            f"\nA saved {saved_command} task is still pending (run --continue to resume it). "
            f"Starting --{command_name} now will discard it. Overwrite? [Y/n]: "
        ).strip().lower()
        if answer in ("", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")
