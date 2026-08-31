"""
Config-folder storage: where per-setting .config files live, and the
generic read/write helpers used by every --config subcommand.
"""

import json

from .state import PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME, DEFAULTS, GITHUB_BRANCH

# Set by cmd_config_delay() (in modes/config_cmd.py) when the user changes
# the delay, and lazily populated on first read by get_request_delay(). A
# module attribute (not a bare global) so both this module and
# modes/config_cmd.py can update the same cached value.
_CONFIG_DELAY = None

# Same pattern as _CONFIG_DELAY, but for the GitHub branch --upgrade
# downloads from and the update checker compares against. Set by
# modes/release.py's cmd_set_release_branch() when the user runs
# --release <branch>, and lazily populated on first read by
# get_release_branch().
_CONFIG_RELEASE_BRANCH = None

def config_dir_state():
    visible = PACKAGE_DIR / CONFIG_DIR_VISIBLE_NAME
    if visible.is_dir():
        return "visible", visible
    return "hidden", PACKAGE_DIR / CONFIG_DIR_HIDDEN_NAME

def current_config_dir():
    return config_dir_state()[1]

_RED = "\033[91m"
_RESET = "\033[0m"

def warn_red(message):
    print(f"{_RED}⚠ {message}{_RESET}")

def config_path(name):
    return current_config_dir() / f"{name}.config"

def load_config_value(name, default=None):
    path = config_path(name)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_config_value(name, value):
    current_config_dir().mkdir(exist_ok=True)
    config_path(name).write_text(json.dumps(value, indent=2), encoding="utf-8")

def get_request_delay():
    global _CONFIG_DELAY
    if _CONFIG_DELAY is None:
        _CONFIG_DELAY = load_config_value("delay", default=DEFAULTS["request_delay"])
    return _CONFIG_DELAY

def get_release_branch():
    """
    Returns the GitHub branch --upgrade downloads from and the passive/
    manual update checker (fetch_remote_version) compares your installed
    version against. Defaults to GITHUB_BRANCH (the repo's normal default
    branch, e.g. "main") until overridden by running --release <branch>,
    which persists the choice in local config the same way --config
    --delay persists the request delay -- so it's remembered across runs,
    not just for the current invocation.
    """
    global _CONFIG_RELEASE_BRANCH
    if _CONFIG_RELEASE_BRANCH is None:
        _CONFIG_RELEASE_BRANCH = load_config_value("release_branch", default=GITHUB_BRANCH)
    return _CONFIG_RELEASE_BRANCH