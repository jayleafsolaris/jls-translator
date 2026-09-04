"""--remove: remove keys from .lang files that are no longer in base."""
import time
from ..common import state
from ..common.state import DEFAULTS, LANGUAGES, _UPDATE_COUNT_MARKER
from ..common.lang_io import parse_lang, write_lang, entries_dict
from ..common.cache import load_cache, save_cache
from ..common.progress import (
    load_base, base_fingerprint, load_progress, save_progress,
    clear_progress, format_duration, _report_keys, _ask_continue,
)
from ..functions.cmd_remove import cmd_remove
