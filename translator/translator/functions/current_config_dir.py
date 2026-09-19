from .config_dir_state import config_dir_state


def current_config_dir():
    return config_dir_state()[1]
