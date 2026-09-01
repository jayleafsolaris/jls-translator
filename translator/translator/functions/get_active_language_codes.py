from ..common.config_store import load_config_value, save_config_value
from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER


def get_active_language_codes():
    active = load_config_value("languages")
    if active is None:
        return list(LANGUAGES.keys())
    return [code for code in LANGUAGES if code in active]
