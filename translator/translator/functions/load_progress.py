from ..common.state import PACKAGE_DIR, DEFAULTS
import json


def load_progress():
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
             return None
    return None
