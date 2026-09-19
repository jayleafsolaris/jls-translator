from ..common.state import PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME, DEFAULTS, GITHUB_BRANCH
from ..common.config_store import _CONFIG_RELEASE_BRANCH
from .load_config_value import load_config_value


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
