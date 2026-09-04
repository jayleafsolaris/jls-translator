from ..common.state import PACKAGE_DIR, DEFAULTS
import json


def save_progress(command, completed, fingerprint, elapsed_time=0.0):
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    path.write_text(
        json.dumps({
            "command": command,
            "completed": completed,
            "fingerprint": fingerprint,
            "elapsed_time": elapsed_time
        }, indent=2),
        encoding="utf-8",
    )
