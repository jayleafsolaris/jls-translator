"""
Config-folder storage: where per-setting .config files live, and the
generic read/write helpers used by every --config subcommand.
"""
import json
from .state import PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME, DEFAULTS, GITHUB_BRANCH
_CONFIG_DELAY = None
_CONFIG_RELEASE_BRANCH = None
_RED = "\033[91m"
_RESET = "\033[0m"
from ..functions.config_dir_state import config_dir_state
from ..functions.config_path import config_path
from ..functions.current_config_dir import current_config_dir
from ..functions.get_release_branch import get_release_branch
from ..functions.get_request_delay import get_request_delay
from ..functions.load_config_value import load_config_value
from ..functions.save_config_value import save_config_value
from ..functions.warn_red import warn_red
