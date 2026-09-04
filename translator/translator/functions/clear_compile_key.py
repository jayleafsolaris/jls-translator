from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
import json
from .load_cache import load_cache


def clear_compile_key():
    """Drops the cached --compile key, e.g. once --decompile has consumed it."""
    cache = load_cache()
    if _COMPILE_KEY_MARKER in cache:
        del cache[_COMPILE_KEY_MARKER]
        cache_path = PACKAGE_DIR / DEFAULTS["cache_file"]
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    return False
