from .cmd_cache_build import cmd_cache_build
from .cmd_cache_clear import cmd_cache_clear
from .cmd_cache_view import cmd_cache_view


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
