from ..common.config_store import load_config_value, save_config_value, current_config_dir
from ..common.github_api import _TOKEN_CONFIG_NAME


def remove_token():
    path = current_config_dir() / f"{_TOKEN_CONFIG_NAME}.config"
    if path.exists():
        path.unlink()
        return True
    return False
