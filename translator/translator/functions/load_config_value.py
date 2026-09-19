import json
from .config_path import config_path


def load_config_value(name, default=None):
    path = config_path(name)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default
