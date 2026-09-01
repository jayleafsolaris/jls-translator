from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
import json
from .load_cache import load_cache


def save_compile_key(key):
    """
    Cache the fresh --compile key so --decompile can recover it later.
    Unlike the --update count, this key never gets written into base
    itself -- base only carries a flag marker (see obfuscate.is_compiled),
    so the cache is the sole source of truth here. If it's lost, the
    compiled base can't be recovered.
    """
    cache = load_cache()
    cache[_COMPILE_KEY_MARKER] = key.hex()
    cache_path = PACKAGE_DIR / DEFAULTS["cache_file"]
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
