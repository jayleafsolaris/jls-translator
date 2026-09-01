"""
Shared runtime constants and mutable state for the jls-translator package.

SCRIPT_DIR is the one piece of genuinely mutable, cross-module state (it's
set once in cli.main() from the current working directory). Every other
module that needs it does ``from . import state`` and reads
``state.SCRIPT_DIR`` rather than importing the name directly, so the value
set in cli.py is visible everywhere.
"""
import hashlib
import re
import sys
from pathlib import Path
try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover -- Python < 3.8 doesn't ship this
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
    "check_cooldown_seconds": 180,  # --check (manual) cooldown, separate from the passive interval above
    "request_delay": 0.15,   # seconds between global translation calls
    "max_retries": 5,
    "workers_min": 1,
    "workers_max": 100,
    "workers_throttle_ceiling": 20,
    "update_limit": 50,      # max number of completed --update runs per base file
    "key_progress_delay": 0.0001,  # seconds paused after each key-by-key progress tick (--add/--remove/--check)
    "translator_reference_section": "Translator References",  # heading name (any depth) whose
        # entries exist purely to be translated for other entries' '{key.path}'
        # cross-references -- never written into any generated .lang file themselves
    "translator_reference_cache_file": ".translator_references.json",  # per-language translated
        # values for the above, kept outside any .lang file since they never live in one
}
SCRIPT_DIR = None  # set at runtime from the saved --path
PACKAGE_DIR = Path(__file__).resolve().parent
GITHUB_OWNER = "jayleafsolaris"
GITHUB_REPO = "jls-translator"
GITHUB_BRANCH = "stable"
PACKAGE_NAME = "roe_translator"
_UPDATE_COUNT_MARKER = hashlib.sha256(
    f"{PACKAGE_NAME}:{GITHUB_REPO}:{GITHUB_OWNER}:update_count".encode("utf-8")
).hexdigest()[:25]
_COMPILE_KEY_MARKER = hashlib.sha256(
    f"{PACKAGE_NAME}:{GITHUB_REPO}:{GITHUB_OWNER}:compile_key".encode("utf-8")
).hexdigest()[:25]
_FALLBACK_VERSION = "?.?.?"  # only used if neither pip metadata nor pyproject.toml resolve a version
from ..functions.get_script_version import get_script_version
SCRIPT_VERSION = get_script_version()
CONFIG_DIR_HIDDEN_NAME = ".config"
CONFIG_DIR_VISIBLE_NAME = "configuration"
GB_CONVERT = "__gb_spelling__"
LANGUAGES = {
    "en_US": None,        # English (US) — untranslated copy of base
    "id_ID": "id",        # Indonesian
    "da_DK": "da",        # Danish
    "de_DE": "de",        # German
    "en_GB": GB_CONVERT,  # English (GB) — base run through British spelling conventions
    "es_ES": "es",        # Spanish
    "es_MX": "es",        # Mexican Spanish
    "fr_CA": "fr",        # Canadian French
    "fr_FR": "fr",        # French
    "it_IT": "it",        # Italian
    "hu_HU": "hu",        # Hungarian
    "nl_NL": "nl",        # Dutch
    "nb_NO": "no",        # Norwegian (Bokmål)
    "pl_PL": "pl",        # Polish
    "pt_BR": "pt",        # Brazilian Portuguese
    "pt_PT": "pt",        # Portuguese
    "sk_SK": "sk",        # Slovak
    "fi_FI": "fi",        # Finnish
    "sv_SE": "sv",        # Swedish
    "tr_TR": "tr",        # Turkish
    "cs_CZ": "cs",        # Czech
    "el_GR": "el",        # Greek
    "bg_BG": "bg",        # Bulgarian
    "ru_RU": "ru",        # Russian
    "uk_UA": "uk",        # Ukrainian
    "ja_JP": "ja",        # Japanese
    "zh_CN": "zh-CN",     # Chinese (Simplified)
    "zh_TW": "zh-TW",     # Chinese (Traditional)
    "ko_KR": "ko",        # Korean
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
