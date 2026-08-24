"""
Translation cache (last-known base values), the --update run-count
marker, languages.json, and worker/active-language resolution.
"""

import json
import os

from . import state
from .state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER
from .lang_io import (
    parse_lang, write_lang, strip_update_count_markers,
    _update_count_comment_prefix, read_update_count_from_base,
)
from .config_store import load_config_value, save_config_value

def load_cache():
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_cache(base_values):
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    path.write_text(json.dumps(base_values, ensure_ascii=False, indent=2), encoding="utf-8")

def clear_cache():
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    if path.exists():
        path.unlink()
        return True
    return False


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

def write_languages_json():
    codes = [c for c in LANGUAGES if (state.SCRIPT_DIR / f"{c}.lang").exists()]
    path = PACKAGE_DIR / DEFAULTS["languages_json"]
    path.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")

def compute_auto_workers():
    cpu = os.cpu_count() or 4
    return max(5, min(20, cpu * 4))

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

def get_active_language_codes():
    active = load_config_value("languages")
    if active is None:
        return list(LANGUAGES.keys())
    return [code for code in LANGUAGES if code in active]

def save_active_language_codes(codes):
    save_config_value("languages", [code for code in LANGUAGES if code in codes])
