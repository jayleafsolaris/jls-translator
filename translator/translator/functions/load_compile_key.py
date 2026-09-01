from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
from .load_cache import load_cache


def load_compile_key():
    """Returns the cached --compile key as bytes, or None if there isn't one."""
    cache = load_cache()
    key_hex = cache.get(_COMPILE_KEY_MARKER)
    if key_hex is None:
        return None
    try:
        return bytes.fromhex(key_hex)
    except ValueError:
        return None
