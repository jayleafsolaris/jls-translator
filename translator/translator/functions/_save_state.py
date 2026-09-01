import json
from ..common.ratelimit import _STATE_FILE


def _save_state(data):
    try:
        _STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
