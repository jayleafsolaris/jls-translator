from ..common.state import PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME, DEFAULTS, GITHUB_BRANCH


def config_dir_state():
    visible = PACKAGE_DIR / CONFIG_DIR_VISIBLE_NAME
    if visible.is_dir():
        return "visible", visible
    return "hidden", PACKAGE_DIR / CONFIG_DIR_HIDDEN_NAME
