from ..common.state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
import json


def _save_version_check_cache(data):
    path = PACKAGE_DIR / DEFAULTS["version_check_file"]
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
