from ..common import state


def debug_log_path():
    """__debug-log.json lives in the current project folder -- the same
    directory as base -- not next to the installed package, so it's easy
    to find and doesn't get mixed up across different projects sharing
    one install (see common/state.py's PACKAGE_DIR vs SCRIPT_DIR)."""
    return state.SCRIPT_DIR / "__debug-log.json"
