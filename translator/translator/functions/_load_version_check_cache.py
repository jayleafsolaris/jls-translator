from ..common.state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
import json


def _load_version_check_cache():
    path = PACKAGE_DIR / DEFAULTS["version_check_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}
