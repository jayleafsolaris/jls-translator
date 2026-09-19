from ..common import state, config_store
from ..common.config_store import load_config_value, save_config_value, get_request_delay, config_dir_state
from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME
from ._set_windows_hidden_attribute import _set_windows_hidden_attribute


def cmd_config_show():
    state, path = config_dir_state()
    if not path.exists():
        print("No config folder exists yet -- run --config --workers or "
              "--config --languages first, then you can toggle its visibility.")
        return
    if state == "visible":
        print(f"Config folder is already visible: {path.name}/")
        return

    target = PACKAGE_DIR / CONFIG_DIR_VISIBLE_NAME
    if target.exists():
        print(f"Can't make it visible -- a '{target.name}' folder already exists here for another reason.")
        return

    path.rename(target)
    _set_windows_hidden_attribute(target, hidden=False)
    print(f"Config folder is now visible: {target.name}/")
