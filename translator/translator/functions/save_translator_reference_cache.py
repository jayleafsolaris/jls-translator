from ..common.state import PACKAGE_DIR, DEFAULTS
import json


def save_translator_reference_cache(data):
    path = PACKAGE_DIR / DEFAULTS["translator_reference_cache_file"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
