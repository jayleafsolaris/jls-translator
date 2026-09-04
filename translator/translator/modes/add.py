"""--add: only add missing keys (no change detection, no network calls)."""
import time
from ..common import state
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT
from ..common.lang_io import parse_lang, write_lang, entries_dict, strip_comments_for_output
from ..common.text_protect import to_british
from ..common.cache import get_active_language_codes, write_languages_json
from ..common.progress import (
    load_base, sync_en_us_from_base, base_fingerprint, load_progress,
    save_progress, clear_progress, format_duration, _report_keys, _ask_continue,
)
from ..functions.cmd_add import cmd_add
