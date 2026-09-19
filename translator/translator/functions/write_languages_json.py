from ..common import state
from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
import json


def write_languages_json():
    codes = [c for c in LANGUAGES if (state.SCRIPT_DIR / f"{c}.lang").exists()]
    path = PACKAGE_DIR / DEFAULTS["languages_json"]
    path.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")
