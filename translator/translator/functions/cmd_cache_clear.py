from ..common.cache import save_cache, get_update_count, write_update_count, clear_cache, load_cache
from ..common.progress import load_base, clear_progress, _human_size
from ..common.state import DEFAULTS, PACKAGE_DIR


def cmd_cache_clear():
    cleared = []
    if clear_progress():
        cleared.append(DEFAULTS["progress_file"])
    if clear_cache():
        cleared.append(DEFAULTS["cache_file"])

    if not cleared:
        print("Nothing to clear -- no saved progress or cache found.")
        return

    print("Cleared:")
    for name in cleared:
        print(f"  {name}")
    print(
         "\n.lang files and lang_backups/ are untouched. --continue now has "
        "nothing to resume, and the next --update will re-check every key "
        "once --create/--update/--add rebuilds the cache."
    )
    print(
        "\nNote: the --update run count marker at the bottom of base is "
        "untouched by this -- it's only reset by --create."
    )
