from ..common import state
from ..common.lang_io import parse_lang, write_lang, strip_update_count_markers, _update_count_comment_prefix, read_update_count_from_base
from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
from .load_cache import load_cache
from .write_update_count import write_update_count


def get_update_count():
    """
    Resolves the current --update count for this base file. Prefers the
    marker comment stored at the bottom of base; if it's missing there but
    still present in the cache, the cached count is re-added to base right
    away (self-healing) so the two stay in sync, and that recovered value
    is returned. Returns 0 if neither has a record of it.
    """
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    base_lines = parse_lang(base_path)
    from_base = read_update_count_from_base(base_lines)
    if from_base is not None:
        return from_base

    cache = load_cache()
    cached_raw = cache.get(_UPDATE_COUNT_MARKER)
    if cached_raw is not None:
        try:
            count = int(cached_raw)
        except (TypeError, ValueError):
            count = 0
        write_update_count(count)  # re-add the missing marker to base
        return count

    return 0
