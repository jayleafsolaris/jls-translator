from .current_config_dir import current_config_dir


def config_path(name):
    return current_config_dir() / f"{name}.config"
