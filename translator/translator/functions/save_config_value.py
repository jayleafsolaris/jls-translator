import json
from .config_path import config_path
from .current_config_dir import current_config_dir


def save_config_value(name, value):
    current_config_dir().mkdir(exist_ok=True)
    config_path(name).write_text(json.dumps(value, indent=2), encoding="utf-8")
