from ..common import state
from ..common.lang_io import parse_lang, write_lang, strip_update_count_markers, _update_count_comment_prefix, read_update_count_from_base
from ..common.state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
import json
from .load_cache import load_cache


def write_update_count(count):
    """
    Persists the running --update count in two places:
      1. As a hidden marker comment appended to the very bottom of the
         base file (source of truth -- survives independent of the cache).
      2. Under the same marker key in the translation cache, so that if
         the marker line is ever removed from base (by hand, a merge, or a
         partial restore), get_update_count() can recover the count from
         cache and re-add it to base instead of silently resetting to zero.

    This reloads base and the cache fresh from disk rather than trusting
    whatever the caller has in memory, since this is the last write before
    a run finishes and shouldn't clobber anything written concurrently.
    """
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    current_lines = parse_lang(base_path)
    stripped = strip_update_count_markers(current_lines)
    while stripped and stripped[-1][0] == "blank":
        stripped.pop()
    marker_line = ("comment", f"{_update_count_comment_prefix()}{count}")
    write_lang(base_path, stripped + [marker_line])

    cache = load_cache()
    cache[_UPDATE_COUNT_MARKER] = str(count)
    cache_path = PACKAGE_DIR / DEFAULTS["cache_file"]
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
