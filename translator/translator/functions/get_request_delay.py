from ..common.state import PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME, DEFAULTS, GITHUB_BRANCH
from ..common.config_store import _CONFIG_DELAY
from .load_config_value import load_config_value


def get_request_delay():
    global _CONFIG_DELAY
    if _CONFIG_DELAY is None:
        _CONFIG_DELAY = load_config_value("delay", default=DEFAULTS["request_delay"])
    return _CONFIG_DELAY
