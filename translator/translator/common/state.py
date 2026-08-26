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

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

DEFAULTS = {
    "base_lang": "base",
    "cache_file": ".translate_cache.json",
    "languages_json": "languages.json",
    "backup_dir": "lang_backups",
    "progress_file": ".translate_progress.json",
    "update_temp_file": ".translate_update_temp.json",
    "version_check_file": ".version_check_cache.json",
    "section_order_cache": ".section_order.json",
    "version_check_interval_minutes": 10,
    "request_delay": 0.15,   # seconds between global translation calls
    "max_retries": 3,
    "workers_min": 1,
    "workers_max": 100,
    "workers_throttle_ceiling": 20,
    "update_limit": 50,      # max number of completed --update runs per base file
    "key_progress_delay": 0.0001,  # seconds paused after each key-by-key progress tick (--add/--remove/--check)
}

SCRIPT_DIR = None  # set at runtime from the saved --path

# Where this script/module itself lives once pip-installed (e.g. inside
# site-packages). Cache, progress tracking, languages.json, the
# section-order cache (see --split/--merge, common/sections.py), and the
# config folder all live here -- next to the package -- rather than
# inside the project folder pointed to by --path. NOTE: this means
# cache/config are shared across every project you point --path at; fine
# for a single ongoing project, but keep in mind if you ever manage
# multiple addons with this same install (in particular, the
# section-order cache only remembers ONE project's split at a time).
PACKAGE_DIR = Path(__file__).resolve().parent

# GitHub repo this script/package is published from -- used both by
# --upgrade (downloads the repo zip) and by the update checker (reads the
# version out of pyproject.toml on the default branch without downloading
# anything else).
GITHUB_OWNER = "jayleafsolaris"
GITHUB_REPO = "jls-translator"
GITHUB_BRANCH = "unstable"

# The pip-installed distribution name -- must match the `name` field under
# [project] in pyproject.toml. Used to read the *installed* version back out
# via package metadata, so SCRIPT_VERSION always matches whatever version
# was actually built into the installed package instead of drifting from a
# second, hand-maintained copy of the number.
PACKAGE_NAME = "roe_translator"

# Hidden marker used to track how many times --update has completed against
# the current base file. Stored as a "##"-prefixed comment at the very
# bottom of base (parse_lang treats "##" lines as opaque comments, never as
# real keys, so this never shows up as a translatable entry) and mirrored
# under the same key in the translation cache, so the count can be
# recovered and re-added to base if that marker line is ever lost (hand
# edit, merge, partial restore, etc). Deterministic (not random) so the
# same marker is found run over run.
_UPDATE_COUNT_MARKER = hashlib.sha256(
    f"{PACKAGE_NAME}:{GITHUB_REPO}:{GITHUB_OWNER}:update_count".encode("utf-8")
).hexdigest()[:25]

_FALLBACK_VERSION = "?.?.?"  # only used if neither pip metadata nor pyproject.toml resolve a version


def get_script_version():
    """
    Reads the running script's version from installed package metadata
    (populated by pip from pyproject.toml's [project] version at install
    time), so there's a single source of truth instead of a hardcoded
    string here that can drift out of sync with pyproject.toml.

    If the package isn't pip-installed (e.g. running the .py file directly,
    such as under a-Shell), importlib metadata has nothing to look up --
    in that case, fall back to reading the version straight out of a
    pyproject.toml sitting next to this script, so --version still reports
    the real version instead of the dev placeholder. Only if that also
    can't be found does it fall back to the placeholder.
    """
    if importlib_metadata is not None:
        try:
            return importlib_metadata.version(PACKAGE_NAME)
        except importlib_metadata.PackageNotFoundError:
            pass
        except Exception:
            pass

    found = _find_pyproject_version()
    if found:
        return found

    return _FALLBACK_VERSION


def _find_pyproject_version(max_levels_up=6):
    """
    Walks upward from this script's own directory looking for a
    pyproject.toml, since in a typical package layout it lives at the repo
    root -- one or more directories above the actual module file (e.g.
    repo/pyproject.toml vs repo/src/roe_translator/translate.py) -- not
    necessarily right next to the script itself.

    Reads the version out of either a PEP 621 `[project]` table or a
    Poetry-style `[tool.poetry]` table, whichever is present. Returns None
    if no pyproject.toml with a parseable version is found within
    max_levels_up directories.
    """
    directory = PACKAGE_DIR
    for _ in range(max_levels_up + 1):
        candidate = directory / "pyproject.toml"
        if candidate.exists():
            try:
                text = candidate.read_text(encoding="utf-8")
            except Exception:
                text = None
            if text:
                # Prefer a version line that appears under [project] or
                # [tool.poetry] specifically, since a pyproject.toml can
                # contain other "version = ..." lines (build-system
                # requirements, tool configs, etc) that aren't the
                # package's own version.
                for table in (r"\[project\]", r"\[tool\.poetry\]"):
                    section = re.search(
                        rf'{table}(.*?)(?=\n\[|\Z)', text, re.DOTALL
                    )
                    if section:
                        match = re.search(
                            r'(?m)^\s*version\s*=\s*"([^"]+)"', section.group(1)
                        )
                        if match:
                            return match.group(1)
                # Fall back to the first bare version line anywhere in the
                # file if neither table matched (unusual pyproject.toml
                # layout) -- better than nothing.
                match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
                if match:
                    return match.group(1)
            # A pyproject.toml exists here but had no usable version --
            # stop climbing rather than risk picking up an unrelated one
            # further up the tree.
            return None
        if directory.parent == directory:
            break
        directory = directory.parent
    return None

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

# Updated to protect actual newlines via __NL__ token during batch splits,
# and to protect {key.path}-style base-value cross-references (e.g.
# {ui.roe:pack.name}) so they're passed through translation untouched,
# just like %1$s-style placeholders and section-sign color codes -- these
# reference another key's value (resolved at runtime, not by this script)
# rather than being translatable text themselves.
TOKEN_PATTERN = re.compile(
    r"__NL__|§.|%\d+\$[a-zA-Z]|%[a-zA-Z]|\{[^{}]+\}|[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]"
)