from ..common.config_store import load_config_value, save_config_value
from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
from .compute_auto_workers import compute_auto_workers


def resolve_workers(text_count):
    configured = load_config_value("workers", default="auto")
    if configured == "auto":
        configured = compute_auto_workers()

    if not text_count:
        return DEFAULTS["workers_min"]

    # Deterministic: roughly a third of the keys needing work this batch,
    # capped by the saved workers config and the throttle ceiling.
    by_keys = max(1, text_count // 3)
    resolved = min(configured, by_keys, DEFAULTS["workers_throttle_ceiling"])
    resolved = max(DEFAULTS["workers_min"], resolved)
    return resolved
