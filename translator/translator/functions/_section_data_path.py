from ..common.state import DEFAULTS, PACKAGE_DIR, _UPDATE_COUNT_MARKER


def _section_data_path():
    return PACKAGE_DIR / DEFAULTS["section_order_cache"]
