from ..common.config_store import load_config_value, save_config_value, current_config_dir
from ..common.github_api import _TOKEN_CONFIG_NAME


def get_token():
    return load_config_value(_TOKEN_CONFIG_NAME, default=None)
