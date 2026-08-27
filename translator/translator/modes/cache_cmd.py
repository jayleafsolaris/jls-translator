"""--cache and its subcommands: rebuild, view info about, or clear the translation cache."""

from ..common.state import DEFAULTS, PACKAGE_DIR
from ..common.progress import load_base, clear_progress, _human_size
from ..common.lang_io import entries_dict
from ..common.cache import save_cache, get_update_count, write_update_count, clear_cache, load_cache

def cmd_cache_build():
    base_lines = load_base()
    base_values = entries_dict(base_lines)
    save_cache(base_values)
    # save_cache() overwrites the whole cache file, so the update-count
    # marker key needs to be re-added afterward or it would be wiped.
    count = get_update_count()
    write_update_count(count)
    print(
        f"Rebuilt {DEFAULTS['cache_file']} from {DEFAULTS['base_lang']} "
        f"({len(base_values)} key(s)), without translating anything."
    )
    print("The next --update will treat these values as the known-good baseline.")


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


def cmd_cache_view():
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    if not path.exists():
        print(f"No cache file found ({DEFAULTS['cache_file']}). "
              f"Run --cache --build, or --create/--update/--add first.")
        return
    cache = load_cache()
    size = path.stat().st_size
    print(f"{path.name:<24}{_human_size(size):>8}   {len(cache)} cached key(s)")


def cmd_cache_menu():
    options = [
        ("build", "Rebuild the cache from the current base file, without translating"),
        ("view", "View info about the cache file (size, key count)"),
        ("clear", "Clear saved progress + the translation cache"),
    ]
    print("Cache -- what would you like to do?\n")
    for i, (key, desc) in enumerate(options, start=1):
        print(f"  {i}. --cache --{key:<8} {desc}")

    while True:
        raw = input(f"\nChoose 1-{len(options)}: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= idx <= len(options):
            key = options[idx - 1][0]
            break
        print(f"Please enter a number between 1 and {len(options)}.")

    print()
    if key == "build":
        cmd_cache_build()
    elif key == "view":
        cmd_cache_view()
    elif key == "clear":
        cmd_cache_clear()

