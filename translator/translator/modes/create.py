"""--create: overwrite all active .lang files from scratch."""
import time
from ..common import state
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT
from ..common.lang_io import strip_comments_for_output, entries_dict, write_lang
from ..common.text_protect import to_british, resolve_key_references
from ..common.netcheck import require_internet_or_warn
from ..common.translate import translate_many
from ..common.ratelimit import set_job_profile, status_report
from ..common.cache import get_active_language_codes, save_cache, write_languages_json, write_update_count, resolve_workers
from ..common.progress import (
    load_base, sync_en_us_from_base, base_fingerprint, load_progress,
    save_progress, clear_progress, format_duration, _report, SmoothProgress,
    _ask_continue,
)
from ..functions.cmd_create import cmd_create
