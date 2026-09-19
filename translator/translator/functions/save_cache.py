from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
import json


def save_cache(base_values):
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    path.write_text(json.dumps(base_values, ensure_ascii=False, indent=2), encoding="utf-8")
