from ..common import state, config_store
from ..common.config_store import load_config_value, save_config_value, get_request_delay, config_dir_state
from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME


def cmd_config_delay():
    current = get_request_delay()
    print(f"Current setting: {current}s between API requests.")
    print("Lowering this speeds up translation but increases the risk of getting throttled (429 errors).")
    print(f"Default is {DEFAULTS['request_delay']}.")

    while True:
        raw = input(f"\nEnter new delay in seconds [{current}]: ").strip()
        if not raw:
            return
        try:
            val = float(raw)
            if val < 0:
                print("Delay cannot be negative.")
                continue
            save_config_value("delay", val)
            config_store._CONFIG_DELAY = val
            print(f"\nSaved: delay = {val}s")
            break
        except ValueError:
            print("Please enter a valid number (e.g. 0.1, 0.05).")
