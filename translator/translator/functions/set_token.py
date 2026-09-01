from ..common.config_store import load_config_value, save_config_value, current_config_dir
import os
from ..common.github_api import _TOKEN_CONFIG_NAME


def set_token(token):
    save_config_value(_TOKEN_CONFIG_NAME, token)
    path = current_config_dir() / f"{_TOKEN_CONFIG_NAME}.config"
    try:
        os.chmod(path, 0o600)  # best-effort -- not every filesystem (e.g. iOS/a-Shell) supports this
    except Exception:
        pass
