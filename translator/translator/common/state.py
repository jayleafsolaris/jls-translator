"""
Shared runtime constants and mutable state for the jls-translator package.

SCRIPT_DIR and _CODE_COMPILE_KEY are the two pieces of genuinely mutable,
cross-module state set once from outside this module rather than computed
here. SCRIPT_DIR is set in cli.main() from the current working directory.
_CODE_COMPILE_KEY is set at cli.py's IMPORT time (not inside main()) from a
literal embedded directly in cli.py -- see cli.py for why. Every other
module that needs either does ``from . import state`` and reads
``state.SCRIPT_DIR`` / ``state._CODE_COMPILE_KEY`` rather than importing the
name directly, so the value set from outside is visible everywhere.
"""
import hashlib
import re
import sys
from pathlib import Path
try:
    from importlib import metadata as importlib_metadata
except ImportError:
    importlib_metadata = None
DEFAULTS = {
    "base_lang": "base",
    "cache_file": ".translate_cache.json",
    "languages_json": "languages.json",
    "backup_dir": "lang_backups",
    "progress_file": ".translate_progress.json",
    "update_temp_file": ".translate_update_temp.json",
    "version_check_file": ".version_check_cache.json",
    "section_order_cache": ".section_order.json",
    "base_backup_file": ".base_backup.txt",
    "ratelimit_file": ".ratelimit_state.json",
    "version_check_interval_minutes": 10,
    "check_cooldown_seconds": 180,
    "request_delay": 0.15,
    "max_retries": 5,
    "workers_min": 1,
    "workers_max": 100,
    "workers_throttle_ceiling": 20,
    "update_limit": 50,
    "key_progress_delay": 0.0001,
    "translator_reference_section": "Translator References",
    "translator_reference_cache_file": ".translator_references.json",
}
SCRIPT_DIR = None
_CODE_COMPILE_KEY = None
PACKAGE_DIR = Path(__file__).resolve().parent
GITHUB_OWNER = "jayleafsolaris"
GITHUB_REPO = "jls-translator"
GITHUB_BRANCH = "unstable"
PACKAGE_NAME = "roe_translator"
_UPDATE_COUNT_MARKER = hashlib.sha256(
    f"{PACKAGE_NAME}:{GITHUB_REPO}:{GITHUB_OWNER}:update_count".encode("utf-8")
).hexdigest()[:25]
_COMPILE_KEY_MARKER = hashlib.sha256(
    f"{PACKAGE_NAME}:{GITHUB_REPO}:{GITHUB_OWNER}:compile_key".encode("utf-8")
).hexdigest()[:25]
_CODE_COMPILE_KEY_MARKER = hashlib.sha256(
    f"{PACKAGE_NAME}:{GITHUB_REPO}:{GITHUB_OWNER}:code_compile_key".encode("utf-8")
).hexdigest()[:25]
_CLI_KEY_TAG = hashlib.sha256(
    f"{PACKAGE_NAME}:{GITHUB_REPO}:{GITHUB_OWNER}:cli_key_tag".encode("utf-8")
).hexdigest()[:25]
_FALLBACK_VERSION = "?.?.?"
from ..functions.get_script_version import get_script_version
SCRIPT_VERSION = get_script_version()
CONFIG_DIR_HIDDEN_NAME = ".config"
CONFIG_DIR_VISIBLE_NAME = "configuration"
GB_CONVERT = "__gb_spelling__"
LANGUAGES = {
    "en_US": None,
    "id_ID": "id",
    "da_DK": "da",
    "de_DE": "de",
    "en_GB": GB_CONVERT,
    "es_ES": "es",
    "es_MX": "es",
    "fr_CA": "fr",
    "fr_FR": "fr",
    "it_IT": "it",
    "hu_HU": "hu",
    "nl_NL": "nl",
    "nb_NO": "no",
    "pl_PL": "pl",
    "pt_BR": "pt",
    "pt_PT": "pt",
    "sk_SK": "sk",
    "fi_FI": "fi",
    "sv_SE": "sv",
    "tr_TR": "tr",
    "cs_CZ": "cs",
    "el_GR": "el",
    "bg_BG": "bg",
    "ru_RU": "ru",
    "uk_UA": "uk",
    "ja_JP": "ja",
    "zh_CN": "zh-CN",
    "zh_TW": "zh-TW",
    "ko_KR": "ko",
}
LANGUAGE_NAMES = {
    "en_US": "English (US)", "id_ID": "Indonesian", "da_DK": "Danish", "de_DE": "German",
    "en_GB": "English (GB)", "es_ES": "Spanish", "es_MX": "Mexican Spanish",
    "fr_CA": "Canadian French", "fr_FR": "French", "it_IT": "Italian",
    "hu_HU": "Hungarian", "nl_NL": "Dutch", "nb_NO": "Norwegian (Bokmål)",
    "pl_PL": "Polish", "pt_BR": "Brazilian Portuguese", "pt_PT": "Portuguese",
    "sk_SK": "Slovak", "fi_FI": "Finnish", "sv_SE": "Swedish", "tr_TR": "Turkish",
    "cs_CZ": "Czech", "el_GR": "Greek", "bg_BG": "Bulgarian", "ru_RU": "Russian",
    "uk_UA": "Ukrainian", "ja_JP": "Japanese", "zh_CN": "Chinese (Simplified)",
    "zh_TW": "Chinese (Traditional)", "ko_KR": "Korean",
}
TOKEN_PATTERN = re.compile(
    r"__NL__|§.|%\d+\$[a-zA-Z]|%[a-zA-Z]|\{[^{}]+\}|[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]"
)
from ..functions._find_pyproject_version import _find_pyproject_version
