from ..common.state import PACKAGE_DIR, DEFAULTS


def clear_progress():
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    if path.exists():
        path.unlink()
        return True
    return False
