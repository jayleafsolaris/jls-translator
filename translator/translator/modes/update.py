"""--update: retranslate changed keys already present in each .lang file."""
import contextlib
import json
import random
import sys
import time
import traceback
from ..common import state
from ..common import ratelimit as ratelimit_mod
from ..common import translate as translate_mod
from ..common.state import DEFAULTS, LANGUAGES, GB_CONVERT, PACKAGE_DIR
from ..common.lang_io import parse_lang, write_lang, entries_dict
from ..common.text_protect import tokens_only_diff, apply_token_patch, to_british, resolve_key_references
from ..common.netcheck import require_internet_or_warn
from ..common.config_store import warn_red
from ..common.translate import translate_many, reset_outage_state
from ..common.ratelimit import set_job_profile, status_report
from ..common.cache import load_cache, save_cache, get_update_count, write_update_count, write_languages_json, get_active_language_codes, resolve_workers
from ..common.progress import (
    load_base, sync_en_us_from_base, base_fingerprint, clear_progress, save_progress,
    format_duration, SmoothProgress, _report_keys, _report_finishing,
)
CLR_RED = "\033[31m"
CLR_DARK_GREEN = "\033[32m"
CLR_DIM = "\033[2m"
CLR_RESET = "\033[0m"
# Slow-down severity tiers on the Progress line (see functions/cmd_update.py):
# 1-3 pink, 4-7 orange, 8+ red. Neither pink nor orange exist in the base
# 8-color ANSI palette (which is all CLR_RED/CLR_DARK_GREEN above use), so
# these use 256-color codes instead -- near-universally supported and the
# only way to get an actual pink/orange rather than falling back to
# magenta/yellow, which read as visually different colors entirely.
CLR_PINK = "\033[38;5;213m"
CLR_ORANGE = "\033[38;5;208m"
MAX_SLOW_LEVEL = 15
from ..functions._quiet_warnings import _quiet_warnings
from ..functions._slow_delay import _slow_delay
from ..functions.cmd_update import cmd_update
