from ..common.state import DEFAULTS, PACKAGE_DIR


def _backup_path():
    return PACKAGE_DIR / DEFAULTS["base_backup_file"]
