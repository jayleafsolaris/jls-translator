from ..common.cache import compute_auto_workers, get_active_language_codes, save_active_language_codes
from ..common.config_store import load_config_value, save_config_value, get_request_delay, config_dir_state
from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME


def cmd_config_workers():
    current = load_config_value("workers", default="auto")
    auto_now = compute_auto_workers()

    print(f"Current setting: {current}" + (f" (resolves to {auto_now} right now)" if current == "auto" else ""))
    print(f"\nEnter a number from {DEFAULTS['workers_min']}-{DEFAULTS['workers_max']}, or 'auto' "
          f"to let the script pick based on your CPU and each run's size.")
    print("Higher values translate faster but are more likely to get throttled by Google.\n")

    while True:
        raw = input(f"Workers [{current}]: ").strip().lower()
        if not raw:
            raw = str(current)

        if raw == "auto":
             value = "auto"
             break

        try:
            n = int(raw)
        except ValueError:
            print("Please enter a whole number, or 'auto'.")
            continue

        if not (DEFAULTS["workers_min"] <= n <= DEFAULTS["workers_max"]):
            print(f"Please enter a number between {DEFAULTS['workers_min']} and {DEFAULTS['workers_max']}.")
            continue

        if n > DEFAULTS["workers_throttle_ceiling"]:
            confirm = input(
                f"{n} workers is high and likely to get throttled by Google Translate.\n"
                f"Use it anyway?\n[y/N]: "
            ).strip().lower()
            if confirm not in ("y", "yes"):
                continue

        value = n
        break

    save_config_value("workers", value)

    if value == "auto":
        print(f"\nSaved: workers = auto (currently resolves to {compute_auto_workers()}, "
              f"and will shrink further for languages with fewer keys than that).")
    else:
        print(f"\nSaved: workers = {value} "
              f"(will shrink at runtime if a language has fewer keys than that, or warn/cap if too high).")
