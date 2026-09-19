from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER


def clear_cache():
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    if path.exists():
        path.unlink()
        return True
    return False
