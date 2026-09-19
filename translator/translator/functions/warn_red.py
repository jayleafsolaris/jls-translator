from ..common.config_store import _RED, _RESET


def warn_red(message):
    print(f"{_RED}⚠ {message}{_RESET}")
