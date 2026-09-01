"""
Translation cache (last-known base values), the --update run-count
marker, the --compile key cache, languages.json, and worker/active-language
resolution.
"""
import json
import os
from . import state
from .state import PACKAGE_DIR, DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER, _COMPILE_KEY_MARKER
from .lang_io import (
    parse_lang, write_lang, strip_update_count_markers,
    _update_count_comment_prefix, read_update_count_from_base,
)
from .config_store import load_config_value, save_config_value
from ..functions.clear_cache import clear_cache
from ..functions.clear_compile_key import clear_compile_key
from ..functions.compute_auto_workers import compute_auto_workers
from ..functions.get_active_language_codes import get_active_language_codes
from ..functions.get_update_count import get_update_count
from ..functions.load_cache import load_cache
from ..functions.load_compile_key import load_compile_key
from ..functions.load_translator_reference_cache import load_translator_reference_cache
from ..functions.resolve_workers import resolve_workers
from ..functions.save_active_language_codes import save_active_language_codes
from ..functions.save_cache import save_cache
from ..functions.save_compile_key import save_compile_key
from ..functions.save_translator_reference_cache import save_translator_reference_cache
from ..functions.write_languages_json import write_languages_json
from ..functions.write_update_count import write_update_count
