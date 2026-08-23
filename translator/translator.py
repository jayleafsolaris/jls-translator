#!/usr/bin/env jls-translator

"""
Auto-translates `base` into every language Minecraft
Bedrock supports out of the box (including en_US), and keeps those
.lang files in sync.

`base` (no file extension) is the source-of-truth file you hand-edit.
It's kept separate from every generated .lang file — en_US.lang is
now just a regular output, an untranslated copy of `base`, exactly
like en_GB.lang.

Usage (run from anywhere — pass --path to point at the folder containing
base and your .lang files, e.g. RP/texts/):

    jls-translator --create   overwrite ALL .lang files from scratchr
    jls-translator --update   retranslate changed keys (existing keys only)
    jls-translator --add      only add missing keys (no change detection)
    jls-translator --remove   remove keys no longer in base
    jls-translator --delete   delete every generated .lang file (base is kept)
    jls-translator --backup   zip base + all .lang files into lang_backups/
    jls-translator --restore  restore base + .lang files (+ cache/languages.json)
                                     from a lang_backups/ zip you pick
    jls-translator --view     list base + .lang files in this folder + sizes
    jls-translator --continue resume the last interrupted --create/--update/--add/--remove/--delete run
    jls-translator --cache    manage the translation cache (see below)
    jls-translator --config   manage script configuration (see below)
    jls-translator --upgrade  update the script to the latest version from GitHub
    jls-translator --check    manually check GitHub for a newer version right now
                                     (doesn't change automatic checking)
    jls-translator --check true|false
                              turn the automatic passive update check (the one that
                                     runs quietly on every command) on or off

--path is required for every mode except --version.

Add --ask to --create/--add/--remove/--delete/--continue to be asked after each
language whether to continue or stop, e.g.:

    jls-translator --create --ask

Add --summary to --add/--remove for a full per-language breakdown instead
of just the totals, e.g.:

    jls-translator --add --summary

Progress is saved after every completed language regardless of --ask,
so --continue can also recover from a crash, dropped connection, or force-quit.

--cache holds everything related to the translation cache used by
--update's change detection:

    jls-translator --cache             show the cache menu
    jls-translator --cache --build     rebuild the cache from the current base file...
    jls-translator --cache --view      show info about the cache file
    jls-translator --cache --clear     delete the saved progress file and the translation cache...

--config holds everything that configures how the script behaves, stored as
separate files under a .config/ folder:

    jls-translator --config             show the config menu
    jls-translator --config --workers    set the concurrent worker count
    jls-translator --config --languages  view/edit which are actively translated
    jls-translator --config --delay      set the global translation rate-limit delay
    jls-translator --config --delete     delete the whole config folder (resets all)
    jls-translator --config --show       make the config folder visible
    jls-translator --config --hide       make the config folder hidden

Requires:
    pip install deep_translator requests --user
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import random
import re
import shutil
import string
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover -- Python < 3.8 doesn't ship this
    importlib_metadata = None

# ----------------------------------------------------------------------
# Dependency Check
# ----------------------------------------------------------------------
try:
    import requests
    from deep_translator import GoogleTranslator
except ImportError:
    print("\033[91m\nError: Missing required dependencies.\033[0m")
    print("This script requires 'deep_translator' and 'requests' to run.")
    print("Please install them by running:\n\n    pip install deep_translator requests\n")
    sys.exit(1)


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
# site-packages). Cache, progress tracking, languages.json, and the config
# folder all live here -- next to the package -- rather than inside the
# project folder pointed to by --path. NOTE: this means cache/config are
# shared across every project you point --path at; fine for a single
# ongoing project, but keep in mind if you ever manage multiple addons with
# this same install.
PACKAGE_DIR = Path(__file__).resolve().parent

# GitHub repo this script/package is published from -- used both by
# --upgrade (downloads the repo zip) and by the update checker (reads the
# version out of pyproject.toml on the default branch without downloading
# anything else).
GITHUB_OWNER = "jayleafsolaris"
GITHUB_REPO = "jls-translator"
GITHUB_BRANCH = "main"

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

_FALLBACK_VERSION = "0.0.0-dev"  # only used if neither pip metadata nor pyproject.toml resolve a version


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

# Thread-safe rate limiter variables
_RATE_LIMIT_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0
_CONFIG_DELAY = None

def config_dir_state():
    visible = PACKAGE_DIR / CONFIG_DIR_VISIBLE_NAME
    if visible.is_dir():
        return "visible", visible
    return "hidden", PACKAGE_DIR / CONFIG_DIR_HIDDEN_NAME

def current_config_dir():
    return config_dir_state()[1]

_RED = "\033[91m"
_RESET = "\033[0m"

def warn_red(message):
    print(f"{_RED}⚠ {message}{_RESET}")

def config_path(name):
    return current_config_dir() / f"{name}.config"

def load_config_value(name, default=None):
    path = config_path(name)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_config_value(name, value):
    current_config_dir().mkdir(exist_ok=True)
    config_path(name).write_text(json.dumps(value, indent=2), encoding="utf-8")

def get_request_delay():
    global _CONFIG_DELAY
    if _CONFIG_DELAY is None:
        _CONFIG_DELAY = load_config_value("delay", default=DEFAULTS["request_delay"])
    return _CONFIG_DELAY

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

# Updated to protect actual newlines via __NL__ token during batch splits
TOKEN_PATTERN = re.compile(
    r"__NL__|§.|%\d+\$[a-zA-Z]|%[a-zA-Z]|[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]"
)


# ----------------------------------------------------------------------
# .lang parsing / writing
# ----------------------------------------------------------------------

def parse_lang(path: Path):
    lines = []
    if not path.exists():
        return lines
    with path.open("r", encoding="utf-8") as f:
        for raw in f.read().splitlines():
            stripped = raw.strip()
            if not stripped:
                lines.append(("blank", ""))
                continue
            if stripped.startswith("#"):
                # Any line starting with '#' is a comment -- this covers
                # both '##'/'###' section headers and a single '#' used to
                # disable/comment-out an entry (e.g. '#ui.roe:key=value').
                # Without this, a single-'#' disabled entry that still
                # contains an '=' would otherwise fall through to the
                # entry-parsing branch below and get treated as a real key
                # (with a stray '#' stuck in front of it), which then
                # pollutes key counts, the cache, and generated .lang files.
                lines.append(("comment", raw))
                continue
            if "=" not in raw:
                lines.append(("comment", raw))
                continue
            key, _, rest = raw.partition("=")
            key = key.strip()
            inline_comment = None
            if "\t##" in rest:
                rest, _, inline_comment = rest.partition("\t##")
            lines.append(("entry", key, rest, inline_comment))
    return lines

def entries_dict(lines):
    return {l[1]: l[2] for l in lines if l[0] == "entry"}

def write_lang(path: Path, lines):
    out = []
    for line in lines:
        if line[0] == "blank":
            out.append("")
        elif line[0] == "comment":
            out.append(line[1])
        else:
            _, key, value, inline_comment = line
            if inline_comment is not None:
                out.append(f"{key}={value}\t##{inline_comment}")
            else:
                out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def parse_disabled_entry_key(raw):
    """
    If `raw` is a single-'#' disabled/commented-out entry line (e.g.
    '#ui.roe:key=value') -- as opposed to a '##'/'###' section header or a
    plain '#' note with no '=' in it -- returns the key it disables.
    Returns None for anything else (section headers, plain notes, blank or
    active entry lines).
    """
    stripped = raw.strip()
    if not stripped.startswith("#") or stripped.startswith("##"):
        return None
    body = stripped[1:]
    if "=" not in body:
        return None
    key, _, _ = body.partition("=")
    key = key.strip()
    return key or None


def _update_count_comment_prefix():
    return f"##{_UPDATE_COUNT_MARKER}="


def read_update_count_from_base(base_lines):
    """
    Scans a base file's parsed lines for the hidden --update count marker
    comment and returns its integer value, or None if the marker isn't
    present (or is unparseable) in these lines.
    """
    prefix = _update_count_comment_prefix()
    for line in base_lines:
        if line[0] == "comment" and line[1].strip().startswith(prefix):
            try:
                return int(line[1].strip()[len(prefix):].strip())
            except ValueError:
                continue
    return None


def strip_update_count_markers(base_lines):
    """
    Returns base_lines with any existing --update count marker comment(s)
    removed. Used whenever base's lines are copied out into an actual
    .lang file (en_US.lang, translated output, etc) so the hidden marker
    never leaks into generated, user-facing files -- it only ever belongs
    at the bottom of base itself.
    """
    prefix = _update_count_comment_prefix()
    return [
        line for line in base_lines
        if not (line[0] == "comment" and line[1].strip().startswith(prefix))
    ]


def strip_comments_for_output(base_lines):
    """
    Returns base_lines with EVERY comment line removed -- section headers
    like '## UI' / '### PACK DETAILS', notes, and disabled/commented-out
    entries that start with a bare '#' -- plus the hidden --update count
    marker (which is itself stored as a comment, so it's covered by this
    too).

    Comments are organizational scaffolding for `base` only. They should
    never be copied into an actual, user-facing .lang file -- not the
    untranslated en_US/en_GB copies, and not the real translated
    languages. This is called on base's parsed lines before any of that
    copying happens; `base` itself is never touched by this function.
    """
    return [line for line in base_lines if line[0] != "comment"]


# ----------------------------------------------------------------------
# Translation
# ----------------------------------------------------------------------

def _protect(text):
    tokens = []
    def repl(m):
        tokens.append(m.group(0))
        return f"@@PH{len(tokens) - 1}@@"
    return TOKEN_PATTERN.sub(repl, text), tokens

def _restore(text, tokens):
    def repl(m):
        idx = int(m.group(1))
        return tokens[idx] if idx < len(tokens) else m.group(0)
    return re.sub(r"@\s*@\s*PH\s*(\d+)\s*@\s*@", repl, text, flags=re.IGNORECASE)


def tokens_only_diff(old_text, new_text):
    """
    Compares an old and new base value and checks whether the *only*
    difference between them lives inside protected tokens (%1$s-style
    placeholders, section-sign color codes, PUA glyphs, etc) -- i.e. every
    bit of actual translatable text is byte-for-byte identical, only the
    token(s) themselves changed (a swapped placeholder index, a different
    color code, and so on).

    Returns the new token list (in order) if that's the case, so the caller
    can splice it into an already-translated string instead of retranslating.
    Returns None if there's any other change (meaning a real retranslation
    is needed), including the case where nothing changed at all.
    """
    old_skeleton, old_tokens = _protect(old_text)
    new_skeleton, new_tokens = _protect(new_text)
    if old_skeleton != new_skeleton:
        return None
    if old_tokens == new_tokens:
        return None
    return new_tokens


def apply_token_patch(translated_text, new_tokens):
    """
    Re-applies an updated token list onto an already-translated string
    without calling Google Translate. Only safe when the translated string
    contains the same number of protected tokens as the new base value --
    otherwise we can't line them up positionally, so the caller should fall
    back to a full retranslation. Returns None in that mismatch case.
    """
    skeleton, current_tokens = _protect(translated_text)
    if len(current_tokens) != len(new_tokens):
        return None
    return _restore(skeleton, new_tokens)


BRITISH_SPELLINGS = {
    "color": "colour", "colors": "colours", "colored": "coloured",
    "coloring": "colouring", "colorful": "colourful", "discolor": "discolour",
    "discolored": "discoloured", "favorite": "favourite", "favorites": "favourites", 
    "favor": "favour", "favors": "favours", "favored": "favoured", "favoring": "favouring",
    "honor": "honour", "honors": "honours", "honored": "honoured",
    "honoring": "honouring", "honorable": "honourable", "humor": "humour", 
    "humors": "humours", "humored": "humoured", "humorous": "humourous",
    "flavor": "flavour", "flavors": "flavours", "flavored": "flavoured",
    "flavoring": "flavouring", "behavior": "behaviour", "behaviors": "behaviours",
    "behavioral": "behavioural", "neighbor": "neighbour", "neighbors": "neighbours",
    "neighborhood": "neighbourhood", "neighborhoods": "neighbourhoods",
    "labor": "labour", "labors": "labours", "labored": "laboured",
    "rumor": "rumour", "rumors": "rumours", "armor": "armour", "armors": "armours", 
    "armored": "armoured", "harbor": "harbour", "harbors": "harbours",
    "vapor": "vapour", "vapors": "vapours", "savior": "saviour", "saviors": "saviours",
    "organize": "organise", "organizes": "organises", "organized": "organised", 
    "organizing": "organising", "organization": "organisation", 
    "organizations": "organisations", "realize": "realise", "realizes": "realises", 
    "realized": "realised", "realizing": "realising", "recognize": "recognise", 
    "recognizes": "recognises", "recognized": "recognised", "recognizing": "recognising",
    "apologize": "apologise", "apologizes": "apologises", "apologized": "apologised", 
    "apologizing": "apologising", "customize": "customise", "customizes": "customises",
    "customized": "customised", "customizing": "customising", "customizable": "customisable",
    "analyze": "analyse", "analyzes": "analyses", "analyzed": "analysed",
    "analyzing": "analising", "catalog": "catalogue", "catalogs": "catalogues",
    "dialog": "dialogue", "dialogs": "dialogues", "theater": "theatre", 
    "theaters": "theatres", "center": "centre", "centers": "centres", 
    "centered": "centred", "centering": "centring", "fiber": "fibre", 
    "fibers": "fibres", "defense": "defence", "defenses": "defences",
    "offense": "offence", "offenses": "offences", "license": "licence", 
    "licenses": "licences", "gray": "grey", "grays": "greys", "grayed": "greyed",
    "grayscale": "greyscale", "canceled": "cancelled", "canceling": "cancelling",
    "traveled": "travelled", "traveling": "travelling", "traveler": "traveller", 
    "travelers": "travellers", "modeled": "modelled", "modeling": "modelling",
    "jewelry": "jewellery", "aluminum": "aluminium", "skeptic": "sceptic", 
    "skeptics": "sceptics", "skeptical": "sceptical", "mustache": "moustache", 
    "mustaches": "moustaches", "mold": "mould", "molds": "moulds", 
    "molded": "moulded", "molding": "moulding", "plow": "plough", "plows": "ploughs",
}

_WORD_PATTERN = re.compile(r"[A-Za-z]+")

def _match_case(original_word, replacement):
    if original_word.isupper():
        return replacement.upper()
    if original_word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement

def to_british(text):
    if not text:
        return text
    protected, tokens = _protect(text)
    def repl(m):
        word = m.group(0)
        brit = BRITISH_SPELLINGS.get(word.lower())
        if brit is None:
            return word
        return _match_case(word, brit)
    converted = _WORD_PATTERN.sub(repl, protected)
    return _restore(converted, tokens)


def check_internet(timeout=1.2):
    """
    Quick, cheap connectivity probe. Tries a couple of well-known, highly
    available hosts on their DNS port so we don't depend on Google Translate
    itself (or DNS resolution of a hostname) just to find out whether we're
    online at all.

    The hosts are probed concurrently, not one after another -- a slow or
    silently-dropping connection to one host no longer doubles the wait.
    Worst case is roughly `timeout` seconds total (not `timeout` per host).
    Returns True on the first successful TCP connect, False if every
    attempt fails or times out.
    """
    import socket

    hosts = [("8.8.8.8", 53), ("1.1.1.1", 53)]

    def _try(host_port):
        host, port = host_port
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [ex.submit(_try, hp) for hp in hosts]
        for fut in concurrent.futures.as_completed(futures):
            if fut.result():
                return True
    return False


def require_internet_or_warn(flag_name):
    """
    Call at the top of any command that needs network access (translation
    calls to Google Translate). Warns and returns False if offline, so the
    caller can bail out before doing any work or touching progress/cache
    files.

    Uses a short timeout: both probe hosts are tried concurrently, so an
    offline machine (which fails fast with "network unreachable" or
    "connection refused" rather than hanging) is reported back almost
    instantly. The timeout is only a ceiling for the rarer case of a
    connection that silently drops packets instead of refusing them.
    """
    if check_internet(timeout=0.6):
        return True
    warn_red(
        f"No internet connection detected -- {flag_name} needs network access "
        f"to reach Google Translate."
    )
    print("Check your connection and try again. (Offline-only modes like "
          "--view, --backup, --restore, --remove, --delete, --add, --cache, and "
          "--config don't need this.)")
    return False


_YELLOW = "\033[93m"
_BLUE = "\033[94m"


def fetch_remote_version(timeout=4.0):
    """
    Reads just the `version = "..."` line out of pyproject.toml on GitHub's
    default branch, without downloading the whole repo (that's what
    --upgrade is for). Returns None on any failure -- offline, rate-limited,
    the file moved, a bad connection -- so callers can silently skip the
    update notice instead of erroring out over something this minor.
    """
    url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/pyproject.toml"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', resp.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def _parse_version_tuple(version_string):
    """
    Best-effort parse of a dotted version string into a tuple of ints for
    comparison (e.g. '1.5.10' -> (1, 5, 10)), ignoring any non-numeric
    suffix on a segment (e.g. '2rc1' -> 2) so odd version strings don't
    blow up the comparison.
    """
    parts = []
    for chunk in version_string.split("."):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group(0)) if m else 0)
    return tuple(parts)


def _load_version_check_cache():
    path = PACKAGE_DIR / DEFAULTS["version_check_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_version_check_cache(data):
    path = PACKAGE_DIR / DEFAULTS["version_check_file"]
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def check_for_update_notice(force=False):
    """
    Best-effort, silent-on-failure notice printed when a newer version is
    available on GitHub than the one currently installed/running.

    Only reaches out to the network at most once every
    DEFAULTS['version_check_interval_minutes'] minutes (tracked in a small
    cache file next to the package), so this never adds network latency to
    every-day command usage. Pass force=True (used by --version and a bare
    --check) to always check fresh regardless of that interval.

    When a check is due, this makes exactly one short, low-timeout network
    attempt (no separate "are we online" probe beforehand) so an offline
    or slow connection is discovered and given up on quickly instead of
    waiting out two stacked timeouts.

    The passive/automatic check can be turned off entirely with
    `--check false` (see the "autocheck_enabled" flag in the version-check
    cache) -- while off, this function does nothing unless force=True, so
    --version and a bare --check still always work even with autocheck
    disabled.

    Never raises and never blocks a command on a slow/offline connection --
    worst case this simply prints nothing.
    """
    cache = _load_version_check_cache()
    if not force and cache.get("autocheck_enabled", True) is False:
        return
    now = time.time()
    last_checked = cache.get("last_checked", 0)
    interval_seconds = DEFAULTS["version_check_interval_minutes"] * 60

    remote = cache.get("remote_version")
    stale = force or (now - last_checked) > interval_seconds

    if stale:
        # Passive checks stay snappy with a short timeout; a forced check
        # (--version, bare --check) can afford to wait a bit longer for an
        # accurate answer since the user explicitly asked for one.
        fetched = fetch_remote_version(timeout=1.5 if not force else 3.0)
        if fetched:
            remote = fetched
            cache["remote_version"] = remote
            cache["last_checked"] = now
            _save_version_check_cache(cache)
        else:
            # Offline, blocked, slow, or GitHub unreachable -- stay quiet
            # rather than block the command or report a stale result.
            return

    if not remote:
        return

    try:
        is_newer = _parse_version_tuple(remote) > _parse_version_tuple(SCRIPT_VERSION)
    except Exception:
        return

    if is_newer:
        print(f"{_BLUE}⬆ Update available: v{SCRIPT_VERSION} → v{remote} "
              f"-- run --upgrade to update.{_RESET}")


def cmd_check_update():
    """
    Manually, immediately checks GitHub for a newer version -- always hits
    the network (ignoring DEFAULTS['version_check_interval_minutes']) and
    prints the result either way. This is `--check` used with no value.

    Makes exactly one network attempt (fetch_remote_version) rather than a
    separate "are we online" probe followed by the real request, so an
    offline connection is reported quickly instead of after two stacked
    timeouts.

    Purely informational: it does NOT change whether the passive/automatic
    checker keeps running on other commands -- use `--check true` or
    `--check false` for that.
    """
    print("Checking for updates...")
    cache = _load_version_check_cache()

    remote = fetch_remote_version(timeout=3.0)
    now = time.time()

    if not remote:
        warn_red("Couldn't reach GitHub -- no internet connection, or GitHub is unreachable.")
        return

    cache["remote_version"] = remote
    cache["last_checked"] = now
    _save_version_check_cache(cache)

    try:
        is_newer = _parse_version_tuple(remote) > _parse_version_tuple(SCRIPT_VERSION)
    except Exception:
        is_newer = None

    if is_newer:
        print(f"{_BLUE}⬆ Update available: v{SCRIPT_VERSION} → v{remote} "
              f"-- run --upgrade to update.{_RESET}")
    elif is_newer is False:
        print(f"Up to date: v{SCRIPT_VERSION} is the latest version.")
    else:
        print(f"Current version: v{SCRIPT_VERSION} (latest on GitHub: v{remote}, couldn't compare).")


def cmd_set_autocheck(enabled):
    """
    Turns the passive/automatic update check (the one that silently runs
    at the top of every command) on or off, via `--check true` / `--check
    false`. Does not itself hit the network or change the cached remote
    version -- it only flips the stored flag that check_for_update_notice()
    consults.
    """
    cache = _load_version_check_cache()
    cache["autocheck_enabled"] = enabled
    _save_version_check_cache(cache)
    if enabled:
        print(f"Automatic update checks are now ON (checks at most every "
              f"{DEFAULTS['version_check_interval_minutes']} minutes).")
    else:
        print("Automatic update checks are now OFF. Run --check anytime to check manually.")


def get_translator(google_code):
    return GoogleTranslator(source="en", target=google_code)


def translate_value(google_code, text):
    global _LAST_REQUEST_TIME
    if not text.strip():
        return text
    protected, tokens = _protect(text)
    last_err = None
    delay = get_request_delay()
    
    for attempt in range(DEFAULTS["max_retries"]):
        try:
            translator = get_translator(google_code)
            
            with _RATE_LIMIT_LOCK:
                now = time.time()
                elapsed = now - _LAST_REQUEST_TIME
                if elapsed < delay:
                    time.sleep(delay - elapsed)
                _LAST_REQUEST_TIME = time.time()

            result = translator.translate(protected)
            return _restore(result, tokens)
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    warn_red(f"Translation failed for '{google_code}' after {DEFAULTS['max_retries']} attempts "
             f"({last_err!r}); falling back to untranslated text.")
    return text


def translate_many(google_code, texts, max_workers, progress_cb=None):
    results = [None] * len(texts)
    if not texts:
        return results

    # Filter out empty strings beforehand to optimize network requests
    valid_indices = [i for i, t in enumerate(texts) if t.strip()]
    for i in range(len(texts)):
        if not texts[i].strip():
            results[i] = texts[i]

    if not valid_indices:
        if progress_cb:
            progress_cb(len(texts))
        return results

    # Batch configurations
    MAX_BATCH_CHARS = 2500
    batches = []
    current_batch = []
    current_len = 0

    MIN_BATCH_FLOOR = 8
    desired_min_batches = min(len(valid_indices), MIN_BATCH_FLOOR)
    target_batch_count = min(len(valid_indices), max(max_workers, desired_min_batches))
    items_per_batch = max(1, -(-len(valid_indices) // target_batch_count))  # ceil div

    # Group strings into batches using newlines
    for idx in valid_indices:
        text_clean = texts[idx].replace('\n', '__NL__')

        if current_batch and (
            current_len + len(text_clean) > MAX_BATCH_CHARS
            or len(current_batch) >= items_per_batch
        ):
            batches.append(current_batch)
            current_batch = []
            current_len = 0

        current_batch.append((idx, text_clean))
        current_len += len(text_clean) + 1  # +1 for the joining \n

    if current_batch:
        batches.append(current_batch)

    done_count = len(texts) - len(valid_indices)

    def translate_batch_worker(batch):
        # We join by newline. Google Translator translates sentences separately and natively returns them separated by \n
        combined = "\n".join(t for _, t in batch)
        try:
            translated = translate_value(google_code, combined)
            lines = [line.replace('\r', '') for line in translated.split('\n')]
            
            # Perfect split match
            if len(lines) == len(batch):
                for i, (idx, _) in enumerate(batch):
                    results[idx] = lines[i].replace('__NL__', '\n')
            else:
                # Fallback: if translation split structure shifted, do them independently
                for idx, t in batch:
                    res = translate_value(google_code, t)
                    results[idx] = res.replace('__NL__', '\n')
        except Exception:
            # Fallback on total failure
            for idx, t in batch:
                res = translate_value(google_code, t)
                results[idx] = res.replace('__NL__', '\n')
        return len(batch)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(translate_batch_worker, b) for b in batches]
        for fut in concurrent.futures.as_completed(futures):
            done_count += fut.result()
            if progress_cb:
                progress_cb(done_count)

    return results


# ----------------------------------------------------------------------
# Config / State Methods
# ----------------------------------------------------------------------

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
    base_path = SCRIPT_DIR / DEFAULTS["base_lang"]
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
    base_path = SCRIPT_DIR / DEFAULTS["base_lang"]
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
    codes = [c for c in LANGUAGES if (SCRIPT_DIR / f"{c}.lang").exists()]
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

def cmd_config_workers():
    current = load_config_value("workers", default="auto")
    auto_now = compute_auto_workers()

    print(f"Current setting: {current}" + (f" (resolves to {auto_now} right now)" if current == "auto" else ""))
    print(f"\nEnter a number from {DEFAULTS['workers_min']}-{DEFAULTS['workers_max']}, or 'auto' "
          f"to let the script pick based on your CPU and each run's size.")
    print("Higher values translate faster but are more likely to get throttled by Google.\n")

    while True:
        raw = input(f"Workers [{current}]: ").strip().lower()
        if not raw:
            raw = str(current)

        if raw == "auto":
             value = "auto"
             break

        try:
            n = int(raw)
        except ValueError:
            print("Please enter a whole number, or 'auto'.")
            continue

        if not (DEFAULTS["workers_min"] <= n <= DEFAULTS["workers_max"]):
            print(f"Please enter a number between {DEFAULTS['workers_min']} and {DEFAULTS['workers_max']}.")
            continue

        if n > DEFAULTS["workers_throttle_ceiling"]:
            confirm = input(
                f"{n} workers is high and likely to get throttled by Google Translate.\n"
                f"Use it anyway?\n[y/N]: "
            ).strip().lower()
            if confirm not in ("y", "yes"):
                continue

        value = n
        break

    save_config_value("workers", value)

    if value == "auto":
        print(f"\nSaved: workers = auto (currently resolves to {compute_auto_workers()}, "
              f"and will shrink further for languages with fewer keys than that).")
    else:
        print(f"\nSaved: workers = {value} "
              f"(will shrink at runtime if a language has fewer keys than that, or warn/cap if too high).")

def cmd_config_delay():
    current = get_request_delay()
    print(f"Current setting: {current}s between API requests.")
    print("Lowering this speeds up translation but increases the risk of getting throttled (429 errors).")
    print(f"Default is {DEFAULTS['request_delay']}.")

    while True:
        raw = input(f"\nEnter new delay in seconds [{current}]: ").strip()
        if not raw:
            return
        try:
            val = float(raw)
            if val < 0:
                print("Delay cannot be negative.")
                continue
            save_config_value("delay", val)
            global _CONFIG_DELAY
            _CONFIG_DELAY = val
            print(f"\nSaved: delay = {val}s")
            break
        except ValueError:
            print("Please enter a valid number (e.g. 0.1, 0.05).")

def _curses_available():
    try:
        import curses  # noqa: F401
    except ImportError:
        return False
    return sys.stdout.isatty() and sys.stdin.isatty()

def _edit_active_languages_curses(codes, active_set):
    import curses

    def _run(stdscr):
        curses.curs_set(0)
        idx = 0
        top = 0
        selected = set(active_set)
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            stdscr.addstr(0, 0, "Active languages", curses.A_BOLD)
            stdscr.addstr(1, 0, "SPACE toggle  A all/none  ENTER save  Q cancel"[:max(w - 1, 0)])
            visible = max(h - 4, 1)
            if idx < top:
                top = idx
            if idx >= top + visible:
                 top = idx - visible + 1
            for row, code in enumerate(codes[top:top + visible]):
                real_i = top + row
                mark = "[x]" if code in selected else "[ ]"
                name = LANGUAGE_NAMES.get(code, "")
                line = f"{mark} {code:<8} {name}"
                attr = curses.A_REVERSE if real_i == idx else curses.A_NORMAL
                try:
                    stdscr.addstr(row + 3, 2, line[:max(w - 4, 0)], attr)
                except curses.error:
                    pass
            stdscr.refresh()
            key = stdscr.getch()
            if key in (curses.KEY_UP, ord('k'), ord('K')):
                idx = max(0, idx - 1)
            elif key in (curses.KEY_DOWN, ord('j'), ord('J')):
                idx = min(len(codes) - 1, idx + 1)
            elif key == ord(' '):
                if codes[idx] in selected:
                    selected.discard(codes[idx])
                else:
                    selected.add(codes[idx])
            elif key in (ord('a'), ord('A')):
                selected = set() if len(selected) == len(codes) else set(codes)
            elif key in (curses.KEY_ENTER, 10, 13):
                return selected
            elif key in (ord('q'), ord('Q'), 27):
                return None

    return curses.wrapper(_run)

def _edit_active_languages_text(codes, active_set):
    selected = set(active_set)
    while True:
        print()
        for i, code in enumerate(codes, start=1):
            state = "I" if code in selected else "O"
            name = LANGUAGE_NAMES.get(code, "")
            print(f"  {i:>2}. [{state}] {code:<8} {name}")
        print("\n[I] = active (in)   [O] = inactive (out)")
        raw = input(
            "Enter number(s) to toggle (comma-separated), 'a' to toggle all, "
            "'done' to save, 'q' to cancel: "
        ).strip().lower()

        if raw in ("q", "quit", "cancel"):
            return None
        if raw in ("done", "d", ""):
            return selected
        if raw in ("a", "all"):
            selected = set() if len(selected) == len(codes) else set(codes)
            continue

        parts = [p.strip() for p in raw.split(",") if p.strip()]
        idxs = []
        ok = True
        for p in parts:
            if not p.isdigit() or not (1 <= int(p) <= len(codes)):
                print(f"'{p}' isn't a valid number 1-{len(codes)}.")
                ok = False
                break
            idxs.append(int(p))
        if not ok:
            continue

        for i in idxs:
            code = codes[i - 1]
            if code in selected:
                selected.discard(code)
            else:
                selected.add(code)

def cmd_config_languages():
    codes = list(LANGUAGES.keys())
    active = set(get_active_language_codes())

    print(f"{len(active)}/{len(codes)} language(s) active (translated by --create/--update/--add):\n")
    for code in codes:
        state = "I" if code in active else "O"
        exists = (SCRIPT_DIR / f"{code}.lang").exists()
        file_note = "file exists" if exists else "not created yet"
        name = LANGUAGE_NAMES.get(code, "")
        print(f"  [{state}] {code:<8} {name:<24} ({file_note})")

    print("\n[I] = active (in)   [O] = inactive (out)")
    edit = input("\nEdit which languages are active?\n[y/N]: ").strip().lower()
    if edit not in ("y", "yes"):
        return

    result = None
    if _curses_available():
        try:
            result = _edit_active_languages_curses(codes, active)
        except Exception:
            print("Couldn't start the interactive toggle editor here -- falling back to text mode.")
            result = _edit_active_languages_text(codes, active)
    else:
        result = _edit_active_languages_text(codes, active)

    if result is None:
        print("\nNo changes made.")
        return

    save_active_language_codes(result)
    print(f"\nSaved. {len(result)}/{len(codes)} language(s) active.")

    stale = [c for c in codes if c not in result and (SCRIPT_DIR / f"{c}.lang").exists()]
    if stale:
        print("Note: these .lang files already exist but won't be touched by "
              "--create/--update/--add while inactive (still on disk):")
        for c in stale:
            print(f"  {c}.lang")

def cmd_config_delete():
    _, path = config_dir_state()
    if not path.exists():
        print("No config folder exists yet -- nothing has been configured.")
        return

    files = sorted(p.name for p in path.iterdir())
    print(f"This will delete the {path.name}/ folder and reset all settings to defaults:")
    for f in files:
        print(f"  {path.name}/{f}")
    confirm = input("Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    shutil.rmtree(path)
    print("Deleted config folder.\nWorkers is back to 'auto' and all languages are active again.")

def _set_windows_hidden_attribute(path, hidden):
    if os.name != "nt":
        return
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return
        attrs = (attrs | FILE_ATTRIBUTE_HIDDEN) if hidden else (attrs & ~FILE_ATTRIBUTE_HIDDEN)
        ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs)
    except Exception:
        pass

def cmd_config_show():
    state, path = config_dir_state()
    if not path.exists():
        print("No config folder exists yet -- run --config --workers or "
              "--config --languages first, then you can toggle its visibility.")
        return
    if state == "visible":
        print(f"Config folder is already visible: {path.name}/")
        return

    target = PACKAGE_DIR / CONFIG_DIR_VISIBLE_NAME
    if target.exists():
        print(f"Can't make it visible -- a '{target.name}' folder already exists here for another reason.")
        return

    path.rename(target)
    _set_windows_hidden_attribute(target, hidden=False)
    print(f"Config folder is now visible: {target.name}/")

def cmd_config_hide():
    state, path = config_dir_state()
    if not path.exists():
        print("No config folder exists yet -- run --config --workers or "
              "--config --languages first, then you can toggle its visibility.")
        return
    if state == "hidden":
        print(f"Config folder is already hidden: {path.name}/")
        return

    target = PACKAGE_DIR / CONFIG_DIR_HIDDEN_NAME
    if target.exists():
        print(f"Can't hide it -- a '{target.name}' folder already exists here for another reason.")
        return

    path.rename(target)
    _set_windows_hidden_attribute(target, hidden=True)
    print(f"Config folder is now hidden: {target.name}/")

def cmd_config_menu():
    state, path = config_dir_state()
    options = [
        ("workers", "Configure concurrent translation worker count"),
        ("languages", "View/edit which languages are actively translated"),
        ("delay", "Configure the global rate-limit delay (speed)"),
        ("show", "Make the config folder visible"),
        ("hide", "Make the config folder hidden"),
        ("delete", "Delete the entire config folder (reset everything)"),
    ]
    print(f"Config -- what would you like to do?\n(currently {state}: {path.name}/)\n")
    for i, (key, desc) in enumerate(options, start=1):
        print(f"  {i}. --config --{key:<10} {desc}")

    while True:
        raw = input(f"\nChoose 1-{len(options)}: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= idx <= len(options):
            key = options[idx - 1][0]
            break
        print(f"Please enter a number between 1 and {len(options)}.")

    print()
    if key == "workers":
        cmd_config_workers()
    elif key == "languages":
        cmd_config_languages()
    elif key == "delay":
        cmd_config_delay()
    elif key == "show":
        cmd_config_show()
    elif key == "hide":
        cmd_config_hide()
    elif key == "delete":
        cmd_config_delete()

# ----------------------------------------------------------------------
# Progress / Core Utils
# ----------------------------------------------------------------------

def base_fingerprint(base_values):
    blob = json.dumps(base_values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def load_progress():
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
             return None
    return None

def save_progress(command, completed, fingerprint, elapsed_time=0.0):
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    path.write_text(
        json.dumps({
            "command": command,
            "completed": completed,
            "fingerprint": fingerprint,
            "elapsed_time": elapsed_time
        }, indent=2),
        encoding="utf-8",
    )

def clear_progress():
    path = PACKAGE_DIR / DEFAULTS["progress_file"]
    if path.exists():
        path.unlink()
        return True
    return False

def format_duration(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m {secs}s"

def _convert_base_vars(lines):
    """Converts user-friendly {1} syntax in base to Bedrock's %1$s."""
    out = []
    for line in lines:
        if line[0] == "entry":
            # Replaces {1} -> %1$s, {2} -> %2$s, etc.
            new_val = re.sub(r"\{(\d+)\}", r"%\1$s", line[2])
            out.append(("entry", line[1], new_val, line[3]))
        else:
            out.append(line)
    return out

def load_base():
    base_path = SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.exists():
        sys.exit(f"Error: base file not found (expected '{DEFAULTS['base_lang']}' in {SCRIPT_DIR})")
    lines = parse_lang(base_path)
    # Process the lines to convert `{n}` to `%n$s` in memory
    return _convert_base_vars(lines)


# ----------------------------------------------------------------------
# {key.reference} resolution (used by --add)
# ----------------------------------------------------------------------

# Matches any remaining {...} in a base value. Numeric placeholders like
# {1}/{2} have already been converted to %1$s/%2$s by _convert_base_vars
# before this ever runs, so anything still wrapped in {} at this point is
# a reference to another key's value (e.g. {ui.roe:pack.name}), never a
# positional variable.
_KEY_REF_PATTERN = re.compile(r"\{([^{}]+)\}")


def resolve_key_references(base_lines, max_passes=10):
    """
    Resolves {key.name}-style references in base's entry values by
    substituting them with the referenced key's own value.

    Returns (resolved_lines, missing_keys):
      - If every referenced key exists somewhere in base, resolved_lines
        is base_lines with every {key.name} reference replaced by that
        key's (recursively resolved) value, and missing_keys is [].
      - If ANY referenced key doesn't exist in base, resolved_lines is
        None and missing_keys is a sorted list of every such missing key
        -- nothing is resolved in that case, so the caller can abort
        cleanly instead of writing partially-substituted values.

    References to references are resolved iteratively (capped at
    max_passes) so a chain like A -> B -> C still resolves fully; a
    circular reference simply stops changing once nothing's left to
    substitute for a given pass and is left as literal text.
    """
    base_values = entries_dict(base_lines)

    missing = set()
    for value in base_values.values():
        for match in _KEY_REF_PATTERN.finditer(value):
            ref_key = match.group(1).strip()
            if ref_key not in base_values:
                missing.add(ref_key)

    if missing:
        return None, sorted(missing)

    resolved = dict(base_values)
    for _ in range(max_passes):
        changed = False

        def repl(m):
            nonlocal changed
            ref_key = m.group(1).strip()
            changed = True
            return resolved.get(ref_key, m.group(0))

        next_resolved = {}
        for key, value in resolved.items():
            next_resolved[key] = _KEY_REF_PATTERN.sub(repl, value)
        resolved = next_resolved
        if not changed:
            break

    out = []
    for line in base_lines:
        if line[0] == "entry":
            _, key, _, inline_comment = line
            out.append(("entry", key, resolved.get(key, base_values[key]), inline_comment))
        else:
            out.append(line)
    return out, []

def sync_en_us_from_base(base_lines):
    en_us_path = SCRIPT_DIR / "en_US.lang"
    # Strip every comment line (section headers, notes, disabled/commented
    # entries, and the hidden --update count marker) before mirroring base
    # into en_US.lang -- comments belong to base only and should never
    # show up in a generated, user-facing .lang file.
    write_lang(en_us_path, strip_comments_for_output(list(base_lines)))
    return en_us_path

def _report(lang_idx, lang_total, code, key_idx, key_total, start_time=None, prev_elapsed=0.0, note=""):
    overall_pct = ((lang_idx - 1) + (key_idx / key_total if key_total else 1)) / lang_total * 100

    if start_time is not None:
        time_str = format_duration(prev_elapsed + (time.time() - start_time))
    else:
        time_str = format_duration(prev_elapsed)

    is_final = lang_idx >= lang_total and key_idx >= key_total
    if is_final:
        line = f"[{lang_idx}/{lang_total}] {overall_pct:5.1f}% - Time: {time_str}"
    else:
        line = f"[{lang_idx}/{lang_total}] {overall_pct:5.1f}% ({code}) - Time: {time_str}"
    if note:
        line += f" {note}"
    sys.stdout.write("\r" + line.ljust(85))
    sys.stdout.flush()


def _report_keys(action, done, total):
    """
    Prints a clean, single-line progress indicator like 'Adding Keys... [023/643]'.

    Always called once per completed key (never skipped/batched), and
    pauses briefly after each write so the counter is actually visible
    ticking up one-by-one (1, then 2, then 3, ...) instead of flashing by
    too fast to read on fast, local (non-network) commands like --add and
    --remove. See DEFAULTS['key_progress_delay'].
    """
    width = len(str(total)) if total > 0 else 1
    sys.stdout.write(f"\r{action} Keys... [{done:0{width}d}/{total}]".ljust(60))
    sys.stdout.flush()
    delay = DEFAULTS.get("key_progress_delay", 0)
    if delay:
        time.sleep(delay)


class SmoothProgress:
    """
    Eases a progress bar's displayed value toward the latest real ("target")
    value instead of jumping straight to it.
    """

    def __init__(self, key_total, render, tick_interval=0.08, catch_up_seconds=1.0):
        self.key_total = key_total
        self._render = render  # callable(shown_key_idx)
        self._tick_interval = tick_interval
        self._ticks_to_catch_up = max(1, round(catch_up_seconds / tick_interval))
        self._target = 0
        self._shown = 0
        self._step = 0  # fixed per-tick increment for the current linear ramp
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, target):
        """Called (possibly from multiple worker threads) with the latest known progress."""
        with self._lock:
            if target > self._target:
                self._target = target
                # Recompute a fresh, constant step so the climb from here to
                # this new target is a straight line, not a shrinking one.
                gap = target - self._shown
                self._step = max(1, -(-gap // self._ticks_to_catch_up))  # ceil division

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                target = self._target
                shown = self._shown
                step = self._step
            if shown < target:
                shown = min(target, shown + step)
                with self._lock:
                    self._shown = shown
                self._render(shown)
            self._stop.wait(self._tick_interval)

    def finish(self):
        """Ease any remaining gap up to 100%, then stop the ticker thread."""
        self.update(self.key_total)
        # Let the background ticker keep easing toward 100% on its own
        # schedule instead of snapping, then stop it once it arrives.
        while True:
            with self._lock:
                shown = self._shown
            if shown >= self.key_total:
                break
            time.sleep(self._tick_interval)
        self._stop.set()
        self._thread.join(timeout=1.0)


def _ask_continue(code):
    while True:
        answer = input(f"\nFinished {code}. Continue to next? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------

def _upgrade_protected_names():
    """
    Basenames (files or folders) inside PACKAGE_DIR that --upgrade must
    never overwrite, delete, or merge into, no matter what happens to be
    sitting in the downloaded repo zip under the same name.

    This exists because the cache, progress file, languages.json, the
    version-check cache, and the config folder all deliberately live right
    next to the installed package (see the PACKAGE_DIR comment above) --
    the same directory --upgrade copies the fresh GitHub download into. Any
    matching filename in the repo would otherwise silently overwrite the
    user's real cache/config with whatever happens to be committed (or not
    committed at all, which is just as bad), which is exactly the "my
    config got wiped by --upgrade" bug this guards against.
    """
    return {
        DEFAULTS["cache_file"],
        DEFAULTS["languages_json"],
        DEFAULTS["progress_file"],
        DEFAULTS["update_temp_file"],
        DEFAULTS["version_check_file"],
        CONFIG_DIR_HIDDEN_NAME,
        CONFIG_DIR_VISIBLE_NAME,
        "temp_update",  # --upgrade's own scratch dir, in case it ever lingers
    }


def cmd_upgrade():
    """Fetches the latest main.zip from GitHub, replaces current files, and restarts."""
    UPDATE_URL = (
        f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
    )
    
    print("Checking for updates...")
    if not require_internet_or_warn("--upgrade"):
        return

    try:
        response = requests.get(UPDATE_URL, stream=True)
        response.raise_for_status()

        temp_dir = PACKAGE_DIR / "temp_update"
        os.makedirs(temp_dir, exist_ok=True)

        print("Downloading...")
        protected = _upgrade_protected_names()
        skipped = []
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(temp_dir)
            print("Updating...")
            
            # GitHub zips put everything in a root folder like 'jls-translator-main'
            extracted_root = os.path.join(temp_dir, z.namelist()[0])
            
            # Move files from the extracted folder directly into the script's package dir --
            # except anything that would clobber local cache/config/progress state.
            for item in os.listdir(extracted_root):
                if item in protected:
                    skipped.append(item)
                    continue

                src = os.path.join(extracted_root, item)
                dst = os.path.join(PACKAGE_DIR, item)
                
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

        shutil.rmtree(temp_dir)
        print(f"Update complete!")
        if skipped:
            print(f"Left your local cache/config untouched (repo also had: {', '.join(sorted(skipped))}).")
        
        # Strip --upgrade from args so it doesn't loop infinitely upon restart
        new_args = [arg for arg in sys.argv if arg != "--upgrade"]
        if len(new_args) == 1:
            new_args.append("--version") # Just show the version if they ran it raw
            
        os.execv(sys.executable, [sys.executable] + new_args)
        
    except Exception as e:
        warn_red(f"Update failed: {e}")


def cmd_create(resume=False, interactive=False):
    if not require_internet_or_warn("--create"):
        return
    base_lines = load_base()
    # Never propagate comments (section headers, notes, disabled entries)
    # or the hidden --update count marker into generated output files --
    # only the source-of-truth base file should carry any of that.
    template_lines = strip_comments_for_output(base_lines)
    sync_en_us_from_base(base_lines)
    base_values = entries_dict(base_lines)
    key_total = len(base_values)
    active_codes = get_active_language_codes()
    if not active_codes:
        print("No active languages configured. Run --config --languages to activate some first.")
        return
    all_codes = [(code, LANGUAGES[code]) for code in active_codes]
    lang_total = len(all_codes)
    fingerprint = base_fingerprint(base_values)

    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "create":
             print("No interrupted --create run found. Starting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            if progress.get("fingerprint") != fingerprint:
                print(f"Note: {DEFAULTS['base_lang']} has changed since that run was interrupted — "
                      "resuming anyway using the languages already completed.\n")
            print(f"Resuming --create: {len(completed)}/{lang_total} language(s) already done (accumulated time: {format_duration(elapsed_time)}).\n")

    print(f"Translating {key_total} keys into {lang_total} languages...\n")
    start_run_time = time.time()

    for lang_idx, (code, google_code) in enumerate(all_codes, start=1):
        if code in completed:
            continue
        _report(lang_idx, lang_total, code, 0, key_total, start_run_time, elapsed_time)

        if google_code is None:
            out_lines = list(template_lines)

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render, catch_up_seconds=3.0)
            smoother.update(key_total)
            smoother.finish()
        elif google_code == GB_CONVERT:
            out_lines = [
                line if line[0] != "entry" else ("entry", line[1], to_british(line[2]), line[3])
                for line in template_lines
            ]

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render, catch_up_seconds=3.0)
            smoother.update(key_total)
            smoother.finish()
        else:
            values = [line[2] for line in template_lines if line[0] == "entry"]

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render)
            effective_workers = resolve_workers(len(values))
            translated = translate_many(google_code, values, effective_workers, progress_cb=smoother.update)
            smoother.finish()

            out_lines = []
            t_idx = 0
            for line in template_lines:
                if line[0] != "entry":
                    out_lines.append(line)
                    continue
                _, key, _, inline_comment = line
                out_lines.append(("entry", key, translated[t_idx], inline_comment))
                t_idx += 1
        write_lang(SCRIPT_DIR / f"{code}.lang", out_lines)

        completed.append(code)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("create", completed, fingerprint, current_total_time)

        if interactive and lang_idx < lang_total and not _ask_continue(code):
            save_cache(base_values)
            write_languages_json()
            print(f"\nStopped after {code} ({len(completed)}/{lang_total} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()
    save_cache(base_values)
    write_languages_json()
    # A full --create fully regenerates everything from base, so this is
    # the reset point for the --update run counter.
    write_update_count(0)
    print(f"\nDone. Created {lang_total} language files from {DEFAULTS['base_lang']} in {format_duration(total_duration)}.")


_REPORT_TRANSLATING_LOCK = threading.Lock()


def _report_translating(done, total):
    """
    Renders a 3-line progress block:

        Translating [total] keys...
        Keys: #/# (e.g. 012/104)
        Left: #

    Redraws in place on every call by moving the cursor back up to the top
    of the block (rather than the previous single \\r-terminated line).

    --update's translation workers call this concurrently from multiple
    threads (one per in-flight batch). Without serializing the actual
    writes, two threads' "move cursor up" + "print" sequences can interleave
    mid-escape-sequence, which corrupts the redraw -- the header line stops
    getting overwritten and instead stacks a new copy on every call, while
    only the last few lines (whichever thread wrote last) stay in place.
    The lock ensures each call's cursor-move + 4-line redraw happens as one
    atomic unit on stdout.
    """
    width = len(str(total)) if total else 1
    left = max(total - done, 0)
    lines = [
        f"Translating {total} keys...",
        f"Done: {done:0{width}d}",
        f"Left: {left}",
        f"[{done:0{width}d}/{total}]",
    ]
    with _REPORT_TRANSLATING_LOCK:
        if getattr(_report_translating, "_active", False):
            # Move cursor up to the start of the previously drawn block.
            sys.stdout.write(f"\033[{len(lines)}A")
        else:
            _report_translating._active = True
        for line in lines:
            sys.stdout.write("\033[2K" + line + "\n")
        sys.stdout.flush()


def cmd_update(resume=False, interactive=False):
    base_lines = load_base()

    # Enforce the --update run limit *before* touching the network or
    # doing any work -- once a base file has been --update'd this many
    # times, it needs a full --create to regenerate everything cleanly.
    update_count = get_update_count()
    if update_count >= DEFAULTS["update_limit"]:
        warn_red(
            f"--update limit reached ({update_count}/{DEFAULTS['update_limit']}) for this base file."
        )
        print("This file has reached it's maximum update count. Please create a new set of .lang files to remove any leaked or missed translation keys")
        return

    if not require_internet_or_warn("--update"):
        return
    sync_en_us_from_base(base_lines)
    base_values = entries_dict(base_lines)
    cache = load_cache()
    fingerprint = base_fingerprint(base_values)

    active_codes = set(get_active_language_codes())
    existing_codes = [
        code for code in LANGUAGES
        if code in active_codes and (SCRIPT_DIR / f"{code}.lang").exists()
    ]
    if not existing_codes:
        print("No active .lang files to update. Run --create or --add first, "
              "or check --config --languages if you expected some here.")
        return

    # Figure out, for every language at once, exactly which keys need
    # (re)translating. Nothing gets written to a .lang file yet -- that only
    # happens after every translation below is resolved.
    lang_data = {}
    tasks = []
    total_token_patched = 0
    for code in existing_codes:
        google_code = LANGUAGES[code]
        target_path = SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)
        entries = [line for line in target_lines if line[0] == "entry"]

        to_update = []
        token_patched_count = 0

        for i, (_, key, current_value, inline_comment) in enumerate(entries):
            if key not in base_values:
                continue

            changed_in_base = key in cache and cache[key] != base_values[key]
            needs_fill = google_code is not None and current_value.strip() == ""

            if not (changed_in_base or needs_fill):
                continue

            # If the base value only changed inside a protected token --
            # a %1$s-style placeholder, a section-sign color code, a PUA
            # glyph -- and every bit of surrounding translatable text is
            # unchanged, there's nothing to retranslate. Just splice the
            # new token(s) into the already-translated string in place and
            # skip Google Translate for this key/language entirely.
            if changed_in_base and not needs_fill and google_code is not None:
                new_tokens = tokens_only_diff(cache[key], base_values[key])
                if new_tokens is not None:
                    patched = apply_token_patch(current_value, new_tokens)
                    if patched is not None:
                        entries[i] = ("entry", key, patched, inline_comment)
                        token_patched_count += 1
                        continue
                    # Token count in the translated string doesn't match the
                    # new base's token count (translator dropped/duplicated
                    # a placeholder, or the .lang was hand-edited) -- fall
                    # through to a full retranslation instead of guessing.

            to_update.append(i)

        lang_data[code] = {
            "target_path": target_path,
            "target_lines": target_lines,
            "entries": entries,
            "to_update": to_update,
            "token_patched_count": token_patched_count,
        }
        total_token_patched += token_patched_count
        for i in to_update:
            tasks.append({"code": code, "key": entries[i][1], "google_code": google_code})

    total = len(tasks)
    if total == 0 and total_token_patched == 0:
        clear_progress()
        save_cache(base_values)
        print(f"\nNo keys needed updating — all present .lang files already match {DEFAULTS['base_lang']}.")
        return

    if total_token_patched:
        print(f"{total_token_patched} key(s) had only token changes "
              f"-- patched in place, no retranslation needed.\n")

    results = {}
    total_duration = 0.0

    if total:
        # Hidden scratch file: every finished translation lands here first,
        # keyed by language + key, and is only fanned back out into the real
        # .lang files once the whole combined batch is done. This is also
        # what --continue resumes from if a run gets interrupted.
        temp_path = PACKAGE_DIR / DEFAULTS["update_temp_file"]

        if resume and temp_path.exists():
            try:
                saved = json.loads(temp_path.read_text(encoding="utf-8"))
                if saved.get("fingerprint") == fingerprint:
                    results = saved.get("results", {})
            except Exception:
                results = {}
        elif temp_path.exists():
            temp_path.unlink()

        def task_key(code, key):
            return f"{code}\x00{key}"

        def save_temp():
            temp_path.write_text(
                json.dumps({"fingerprint": fingerprint, "results": results}, ensure_ascii=False),
                encoding="utf-8",
            )

        remaining = [t for t in tasks if task_key(t["code"], t["key"]) not in results]
        done_count = total - len(remaining)

        if resume:
            if done_count:
                print(f"Resuming --update: {done_count}/{total} translation(s) already completed.\n")
            else:
                print("No interrupted --update run found (or base changed since) -- starting fresh.\n")

        if interactive:
            print("Note: --ask has no effect on --update -- all languages are now "
                  "translated together as a single batch.\n")

        start_run_time = time.time()
        _report_translating._active = False
        _report_translating(done_count, total)

        # Local (non-network) work first: direct copy (en_US) and British-spelling
        # conversion (en_GB) need no API call at all.
        for t in [t for t in remaining if t["google_code"] in (None, GB_CONVERT)]:
            text = base_values[t["key"]]
            value = text if t["google_code"] is None else to_british(text)
            results[task_key(t["code"], t["key"])] = value
            done_count += 1
            _report_translating(done_count, total)
        save_temp()
        save_progress("update", [], fingerprint, time.time() - start_run_time)

        # Real network translation, grouped by target Google language code (one
        # 'es' batch covers both es_ES and es_MX, for example) but reported as a
        # single running total across every language.
        by_google = {}
        for t in remaining:
            if t["google_code"] in (None, GB_CONVERT):
                continue
            by_google.setdefault(t["google_code"], []).append(t)

        for google_code, group in by_google.items():
            texts = [base_values[t["key"]] for t in group]
            base_offset = done_count

            def _progress_cb(group_done, _base_offset=base_offset):
                _report_translating(_base_offset + group_done, total)

            workers = resolve_workers(len(texts))
            translated = translate_many(google_code, texts, workers, progress_cb=_progress_cb)
            for t, value in zip(group, translated):
                results[task_key(t["code"], t["key"])] = value
            done_count = base_offset + len(group)
            _report_translating(done_count, total)
            save_temp()
            save_progress("update", [], fingerprint, time.time() - start_run_time)

        total_duration = time.time() - start_run_time
        if temp_path.exists():
            temp_path.unlink()

    clear_progress()
    save_cache(base_values)

    # Now fan the finished translations back out into each language's .lang
    # file -- this is the only point any .lang file gets touched. Entries
    # that were already token-patched in place above are written out as-is.
    summary = []
    for code in existing_codes:
        data = lang_data[code]
        entries = data["entries"]
        changed = data["token_patched_count"]
        for i in data["to_update"]:
            _, key, _, inline_comment = entries[i]
            value = results.get(task_key(code, key)) if total else None
            if value is None:
                continue
            entries[i] = ("entry", key, value, inline_comment)
            changed += 1

        out_lines = []
        e_idx = 0
        for line in data["target_lines"]:
            if line[0] != "entry":
                out_lines.append(line)
            else:
                out_lines.append(entries[e_idx])
                e_idx += 1
        write_lang(data["target_path"], out_lines)
        summary.append((code, changed, data["token_patched_count"]))

    # This --update run did real work (translation and/or token patching),
    # so it counts against the run limit. Persist the incremented count to
    # both base (marker comment) and cache.
    new_update_count = update_count + 1
    write_update_count(new_update_count)

    print(f"\nUpdate complete in {format_duration(total_duration)}:")
    for code, changed, patched in summary:
        if patched:
            print(f"  {code}.lang: {changed} key(s) updated ({patched} via token-only patch)")
        else:
            print(f"  {code}.lang: {changed} key(s) updated")

    print(f"\nUpdate count: {new_update_count}/{DEFAULTS['update_limit']}.")
    if new_update_count >= DEFAULTS["update_limit"]:
        warn_red(
            f"--update limit reached ({new_update_count}/{DEFAULTS['update_limit']}) -- "
            f"this base file must be recreated (--create) before --update can run again."
        )


def cmd_add(resume=False, interactive=False, show_summary=False):
    # --add never calls Google Translate -- missing keys are filled in with a
    # direct copy (en_US), a British-spelling conversion (en_GB), or left
    # blank as an untranslated placeholder (run --update afterward to fill
    # those in). None of that needs network access.
    base_lines = load_base()

    # Resolve {key.reference} substitutions in base before anything else.
    # If any referenced key doesn't exist anywhere in base, abort the whole
    # --add run without touching any .lang file -- a half-resolved base
    # would silently write literal "{missing.key}" text into every
    # language, which is worse than just refusing to run.
    resolved_lines, missing_keys = resolve_key_references(base_lines)
    if missing_keys:
        warn_red("Add failed due to missing keys:")
        print(f"[{', '.join(missing_keys)}]")
        return
    base_lines = resolved_lines

    # Never propagate comments (section headers, notes, disabled entries)
    # or the hidden --update count marker into generated output files --
    # only the source-of-truth base file should carry any of that.
    template_lines = strip_comments_for_output(base_lines)
    sync_en_us_from_base(base_lines)
    base_values = entries_dict(base_lines)
    key_total = len(base_values)
    active_codes = get_active_language_codes()
    if not active_codes:
        print("No active languages configured. Run --config --languages to activate some first.")
        return
    all_codes = [(code, LANGUAGES[code]) for code in active_codes]
    lang_total = len(all_codes)
    fingerprint = base_fingerprint(base_values)

    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "add":
            print("No interrupted --add run found.\nStarting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            if progress.get("fingerprint") != fingerprint:
                print(f"Note: {DEFAULTS['base_lang']} has changed since that run was interrupted — "
                      "resuming anyway using the languages already completed.\n")
            print(f"Resuming --add: {len(completed)}/{lang_total} language(s) already done (accumulated time: {format_duration(elapsed_time)}).\n")

    total_keys_to_check = lang_total * key_total
    keys_checked = len(completed) * key_total

    print(f"Adding missing keys...\n")
    start_run_time = time.time()
    summary = []
    total_added_overall = 0
    total_excluded_disabled = 0

    for lang_idx, (code, google_code) in enumerate(all_codes, start=1):
        if code in completed:
            continue

        target_path = SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)
        existing = entries_dict(target_lines)

        # Keys that already exist in this language's file but are
        # disabled/commented-out (a single-'#' line, e.g.
        # '#ui.roe:key=value') -- these count as "already present" for
        # --add's purposes and must NOT get a duplicate active entry added
        # underneath them. The original disabled line is carried forward
        # into the output as-is.
        disabled_map = {}
        for line in target_lines:
            if line[0] == "comment":
                disabled_key = parse_disabled_entry_key(line[1])
                if disabled_key is not None:
                    disabled_map[disabled_key] = line

        entries = []
        added_this_lang = 0
        excluded_this_lang = 0

        for line in template_lines:
            if line[0] != "entry":
                continue

            keys_checked += 1
            _report_keys("Checking", keys_checked, total_keys_to_check)

            _, key, value, inline_comment = line
            if key in existing:
                entries.append(("entry", key, existing[key], inline_comment))
            elif key in disabled_map:
                entries.append(disabled_map[key])
                excluded_this_lang += 1
            else:
                if google_code is None:
                    placeholder = value
                elif google_code == GB_CONVERT:
                    placeholder = to_british(value)
                else:
                    placeholder = ""
                entries.append(("entry", key, placeholder, inline_comment))
                added_this_lang += 1

        total_added_overall += added_this_lang
        total_excluded_disabled += excluded_this_lang

        out_lines = []
        e_idx = 0
        for line in template_lines:
            if line[0] != "entry":
                out_lines.append(line)
            else:
                out_lines.append(entries[e_idx])
                e_idx += 1

        write_lang(target_path, out_lines)
        summary.append((code, added_this_lang, excluded_this_lang))

        completed.append(code)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("add", completed, fingerprint, current_total_time)

        if interactive and lang_idx < lang_total and not _ask_continue(code):
            write_languages_json()
            print(f"\nStopped after {code} ({len(completed)}/{lang_total} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()
    write_languages_json()

    print(f"\n\nAdd complete in {format_duration(total_duration)}:")
    if show_summary:
        for code, added, excluded in summary:
            note = f"  {code}.lang: {added} new key(s) added (untranslated -- run --update to translate)"
            if excluded:
                note += f", {excluded} skipped (already present but disabled with '#')"
            print(note)
    else:
        print(f"  Added {total_added_overall} total missing key(s) across {len(summary)} language(s).")
        if total_excluded_disabled:
            print(f"  Skipped {total_excluded_disabled} key(s) already present but disabled with '#' (not re-added).")


def cmd_continue(interactive=False, show_summary=False):
    progress = load_progress()
    if not progress:
        print("No previous run to continue. Nothing to resume.")
        return

    command = progress.get("command")
    if command == "create":
        cmd_create(resume=True, interactive=interactive)
    elif command == "update":
        cmd_update(resume=True, interactive=interactive)
    elif command == "add":
        cmd_add(resume=True, interactive=interactive, show_summary=show_summary)
    elif command == "remove":
        cmd_remove(resume=True, interactive=interactive, show_summary=show_summary)
    elif command == "delete":
        cmd_delete(resume=True, interactive=interactive)
    else:
        print("Saved progress is unrecognized or corrupted.\n"
              "Re-run --create, --update, --add, --remove, or --delete to start over.")


def cmd_remove(resume=False, interactive=False, show_summary=False):
    base_lines = load_base()
    base_values = entries_dict(base_lines)

    existing_codes = [code for code in LANGUAGES if (SCRIPT_DIR / f"{code}.lang").exists()]
    if not existing_codes:
        print("No .lang files to clean up. Run --create or --add first.")
        return

    fingerprint = base_fingerprint(base_values)
    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "remove":
            print("No interrupted --remove run found. Starting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            print(f"Resuming --remove: {len(completed)}/{len(existing_codes)} language(s) already checked (accumulated time: {format_duration(elapsed_time)}).\n")

    # Pre-calculate totals for the progress bar
    total_keys_to_check = 0
    keys_checked = 0
    for code in existing_codes:
        count = sum(1 for l in parse_lang(SCRIPT_DIR / f"{code}.lang") if l[0] == "entry")
        total_keys_to_check += count
        if code in completed:
            keys_checked += count

    print(f"Removing deprecated keys...\n")
    start_run_time = time.time()
    summary = []
    total_removed = 0

    for lang_idx, code in enumerate(existing_codes, start=1):
        if code in completed:
            continue

        target_path = SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)

        removed_this_lang = 0
        out_lines = []

        for line in target_lines:
            if line[0] == "entry":
                keys_checked += 1
                _report_keys("Checking", keys_checked, total_keys_to_check)

                _, key, value, inline_comment = line

                if key not in base_values:
                    removed_this_lang += 1
                    continue

                out_lines.append(line)
                continue

            if line[0] == "comment":
                # A single-'#' disabled/commented-out entry (e.g.
                # '#ui.roe:key=value') whose key no longer exists in base
                # is just as deprecated as an active entry for that same
                # key -- drop it too. '##' section headers and plain '#'
                # notes (no '=') aren't tied to a key, so they're always
                # kept.
                disabled_key = parse_disabled_entry_key(line[1])
                if disabled_key is not None and disabled_key not in base_values:
                    removed_this_lang += 1
                    continue

            out_lines.append(line)

        write_lang(target_path, out_lines)
        summary.append((code, removed_this_lang))
        total_removed += removed_this_lang

        completed.append(code)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("remove", completed, fingerprint, current_total_time)

        if interactive and lang_idx < len(existing_codes) and not _ask_continue(code):
            print(f"\nStopped after {code} ({len(completed)}/{len(existing_codes)} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()

    cache = load_cache()
    trimmed_cache = {k: v for k, v in cache.items() if k in base_values or k == _UPDATE_COUNT_MARKER}
    if trimmed_cache != cache:
        save_cache(trimmed_cache)

    if total_removed == 0:
        print(f"\n\nNo deprecated keys found — all present .lang files already match {DEFAULTS['base_lang']}'s keys (took {format_duration(total_duration)}).")
    else:
        print(f"\n\nCleanup complete in {format_duration(total_duration)}:")
        if show_summary:
            for code, removed in summary:
                print(f"  {code}.lang: {removed} key(s) removed")
        else:
            print(f"  Removed {total_removed} total key(s) across {len(summary)} language(s).")


def cmd_delete(resume=False, interactive=False):
    targets = [
        p for p in SCRIPT_DIR.glob("*.lang")
        if p.name != DEFAULTS["base_lang"]
    ]

    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "delete":
            print("No interrupted --delete run found.\nStarting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            print(f"Resuming --delete: {len(completed)} file(s) already deleted (accumulated time: {format_duration(elapsed_time)}).\n")

    targets_to_delete = [p for p in targets if p.name not in completed]

    if not targets_to_delete and not resume:
        print("No translated .lang files to delete.")
        return

    if not resume:
        print(f"This will delete {len(targets_to_delete)} file(s):")
        for p in targets_to_delete:
            print(f"  {p.name}")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

    start_run_time = time.time()
    for lang_idx, p in enumerate(targets_to_delete, start=1):
        if p.exists():
            p.unlink()
        
        completed.append(p.name)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("delete", completed, "none", current_total_time)

        sys.stdout.write(f"\rDeleted {p.name}... time: {format_duration(current_total_time)}".ljust(85))
        sys.stdout.flush()

        if interactive and lang_idx < len(targets_to_delete) and not _ask_continue(p.name):
            print(f"\nStopped after {p.name} ({len(completed)} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()
    print(f"\nDeleted {len(completed)} .lang file(s) in {format_duration(total_duration)}. "
          f"The base file ('{DEFAULTS['base_lang']}') was untouched.")


def cmd_backup():
    backup_dir = SCRIPT_DIR / DEFAULTS["backup_dir"]
    backup_dir.mkdir(exist_ok=True)

    base_path = SCRIPT_DIR / DEFAULTS["base_lang"]
    lang_files = sorted(SCRIPT_DIR.glob("*.lang"))
    all_files = ([base_path] if base_path.exists() else []) + lang_files
    if not all_files:
        print(f"No {DEFAULTS['base_lang']} or .lang files found to back up.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"lang_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in all_files:
            zf.write(p, arcname=p.name)
        cache_path = PACKAGE_DIR / DEFAULTS["cache_file"]
        if cache_path.exists():
            zf.write(cache_path, arcname=cache_path.name)
        lj_path = PACKAGE_DIR / DEFAULTS["languages_json"]
        if lj_path.exists():
             zf.write(lj_path, arcname=lj_path.name)

    print(f"Backed up {len(all_files)} file(s) (including {DEFAULTS['base_lang']}) to {zip_path.relative_to(SCRIPT_DIR)}")


def cmd_restore():
    backup_dir = SCRIPT_DIR / DEFAULTS["backup_dir"]
    if not backup_dir.is_dir():
        print(f"No {DEFAULTS['backup_dir']}/ folder found -- nothing to restore from.")
        return

    zips = sorted(backup_dir.glob("lang_backup_*.zip"), reverse=True)
    if not zips:
        print(f"No backup zips found in {DEFAULTS['backup_dir']}/.")
        return

    print("Available backups (most recent first):\n")
    for i, z in enumerate(zips, start=1):
        print(f"  {i}.\n{z.name:<32}{_human_size(z.stat().st_size):>8}")

    while True:
        raw = input(f"\nRestore which one? [1-{len(zips)}] (default 1): ").strip()
        if not raw:
            idx = 1
            break
        try:
            idx = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= idx <= len(zips):
            break
        print(f"Please enter a number between 1 and {len(zips)}.")

    chosen = zips[idx - 1]
    with zipfile.ZipFile(chosen, "r") as zf:
        names = zf.namelist()

    print(f"\nThis will overwrite these files from {chosen.name} if present:")
    for name in names:
        print(f"  {name}")
    confirm = input("\nType 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    with zipfile.ZipFile(chosen, "r") as zf:
        for name in zf.namelist():
            if name in (DEFAULTS["cache_file"], DEFAULTS["languages_json"]):
                dest_dir = PACKAGE_DIR
            else:
                dest_dir = SCRIPT_DIR
            with zf.open(name) as src, open(dest_dir / name, "wb") as dst:
                shutil.copyfileobj(src, dst)

    print(f"\nRestored {len(names)} file(s) from {chosen.name}.")


def _human_size(num_bytes):
    for unit in ("B", "KB", "MB"):
        if num_bytes < 1024:
            return f"{num_bytes:.0f}{unit}" if unit == "B" else f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}GB"


def cmd_view():
    base_path = SCRIPT_DIR / DEFAULTS["base_lang"]
    files = ([base_path] if base_path.exists() else []) + sorted(SCRIPT_DIR.glob("*.lang"))
    if not files:
        print(f"No {DEFAULTS['base_lang']} or .lang files found in this directory.")
        return

    print(f"{'File':<16}{'Size':>10}   Keys")
    print("-" * 40)
    for p in files:
         size = p.stat().st_size
         key_count = len(entries_dict(parse_lang(p)))
         marker = " (base)" if p.name == DEFAULTS["base_lang"] else ""
         print(f"{p.name:<16}{_human_size(size):>10}   {key_count}{marker}")
    if base_path.exists():
        count = get_update_count()
        print(f"\n--update count for this base file: {count}/{DEFAULTS['update_limit']}")


def cmd_cache_build():
    base_lines = load_base()
    base_values = entries_dict(base_lines)
    save_cache(base_values)
    # save_cache() overwrites the whole cache file, so the update-count
    # marker key needs to be re-added afterward or it would be wiped.
    count = get_update_count()
    write_update_count(count)
    print(
        f"Rebuilt {DEFAULTS['cache_file']} from {DEFAULTS['base_lang']} "
        f"({len(base_values)} key(s)), without translating anything."
    )
    print("The next --update will treat these values as the known-good baseline.")


def cmd_cache_clear():
    cleared = []
    if clear_progress():
        cleared.append(DEFAULTS["progress_file"])
    if clear_cache():
        cleared.append(DEFAULTS["cache_file"])

    if not cleared:
        print("Nothing to clear -- no saved progress or cache found.")
        return

    print("Cleared:")
    for name in cleared:
        print(f"  {name}")
    print(
         "\n.lang files and lang_backups/ are untouched. --continue now has "
        "nothing to resume, and the next --update will re-check every key "
        "once --create/--update/--add rebuilds the cache."
    )
    print(
        "\nNote: the --update run count marker at the bottom of base is "
        "untouched by this -- it's only reset by --create."
    )


def cmd_cache_view():
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    if not path.exists():
        print(f"No cache file found ({DEFAULTS['cache_file']}). "
              f"Run --cache --build, or --create/--update/--add first.")
        return
    cache = load_cache()
    size = path.stat().st_size
    print(f"{path.name:<24}{_human_size(size):>8}   {len(cache)} cached key(s)")


def cmd_cache_menu():
    options = [
        ("build", "Rebuild the cache from the current base file, without translating"),
        ("view", "View info about the cache file (size, key count)"),
        ("clear", "Clear saved progress + the translation cache"),
    ]
    print("Cache -- what would you like to do?\n")
    for i, (key, desc) in enumerate(options, start=1):
        print(f"  {i}. --cache --{key:<8} {desc}")

    while True:
        raw = input(f"\nChoose 1-{len(options)}: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= idx <= len(options):
            key = options[idx - 1][0]
            break
        print(f"Please enter a number between 1 and {len(options)}.")

    print()
    if key == "build":
        cmd_cache_build()
    elif key == "view":
        cmd_cache_view()
    elif key == "clear":
        cmd_cache_clear()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

_MODES = [
    ("create", "Overwrite ALL .lang files from scratch"),
    ("update", "Retranslate changed keys (existing keys only)"),
    ("add", "Only add missing keys (no change detection)"),
    ("remove", "Remove keys no longer in base"),
    ("delete", "Delete every generated .lang file (base is kept)"),
    ("backup", "Zip all .lang files into lang_backups/"),
    ("restore", "Restore .lang files from a lang_backups/ zip"),
    ("view", "List .lang files in this folder + sizes"),
    ("cont", "Resume the last interrupted run (any modifying command)"),
    ("cache", "Manage the translation cache (build, view, or clear)"),
    ("config", "Manage script configuration (workers, active languages, delay)"),
    ("upgrade", "Update the script to the latest version from GitHub"),
]
_MODE_FLAG_NAME = {"cont": "--continue"}


def prompt_for_mode():
    print("No mode specified. What would you like to do?\n")
    for i, (key, desc) in enumerate(_MODES, start=1):
        flag = _MODE_FLAG_NAME.get(key, f"--{key}")
        print(f"  {i}. {flag:<12} {desc}")

    while True:
        raw = input(f"\nChoose 1-{len(_MODES)}: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= idx <= len(_MODES):
            return _MODES[idx - 1][0]
        print(f"Please enter a number between 1 and {len(_MODES)}.")


def prompt_for_ask():
    raw = input("Ask for confirmation after each item finishes? [y/N]: ").strip().lower()
    return raw in ("y", "yes")


def main():
    parser = argparse.ArgumentParser(description="Translate base into all Minecraft Bedrock languages (including en_US).")

    # New mode argument implemented
    parser.add_argument("--mode", choices=["lang", "key"], default="lang", 
                        help="Choose batching mode: translate language by language (lang) or key by key (key).")
    
    parser.add_argument("--create", action="store_true", help="overwrite all .lang files from scratch")
    parser.add_argument("--update", action="store_true", help="retranslate changed keys already present in each .lang")
    parser.add_argument("--add", action="store_true", help="only add missing keys, no change detection")
    parser.add_argument("--remove", action="store_true", help="remove keys no longer in base")
    parser.add_argument("--delete", action="store_true",
                         help="alone: delete all generated .lang files (base is kept).\n"
                              "with --config: delete the whole config folder")
    parser.add_argument("--backup", action="store_true", help="zip base + all .lang files")
    parser.add_argument("--restore", action="store_true",
                         help="restore .lang files (and cache/languages.json) from a "
                              "lang_backups/ zip you pick")
    parser.add_argument("--view", action="store_true",
                         help="alone: list .lang files and sizes. "
                              "with --cache: view info about the cache file")
    parser.add_argument("--continue", dest="cont", action="store_true",
                         help="resume the last interrupted modifying run")
    parser.add_argument("--cache", action="store_true",
                         help="manage the translation cache; combine with --build, --view, or --clear")
    parser.add_argument("--build", action="store_true",
                         help="(with --cache) rebuild the cache from the current base file, "
                              "without translating anything")
    parser.add_argument("--clear", action="store_true",
                         help="(with --cache) delete the saved progress file and the translation "
                              "cache (does not touch .lang files or lang_backups/)")
    parser.add_argument("--config", action="store_true",
                         help="manage script configuration; combine with --workers, "
                              "--languages, --delay, --show, --hide, or --delete")
    parser.add_argument("--workers", action="store_true",
                         help="(with --config) configure concurrent translation worker count")
    parser.add_argument("--languages", action="store_true",
                         help="(with --config) view/edit which languages are actively translated")
    parser.add_argument("--delay", action="store_true",
                         help="(with --config) configure the global rate-limit delay")
    parser.add_argument("--show", action="store_true",
                         help="(with --config) make the config folder visible")
    parser.add_argument("--hide", action="store_true",
                         help="(with --config) make the config folder hidden")
    parser.add_argument("--version", action="store_true", help="print the script version and exit")
    parser.add_argument("--check", nargs="?", const="__now__", default=None, metavar="{true,false}",
                         help="with no value: manually check GitHub for a newer version right now "
                              "(does not change automatic checking). "
                              "with true/false: turn the automatic passive update check "
                              "(the one that runs quietly on every command) on or off")
    parser.add_argument("--ask", action="store_true",
                         help="ask after each item whether to continue or stop "
                              "(combine with --create/--update/--add/--remove/--delete/--continue)")
    parser.add_argument("--upgrade", action="store_true", help="update the script to the latest version from GitHub")
    parser.add_argument("--summary", action="store_true", help="show detailed per-language results for --add and --remove")
    
    args = parser.parse_args()

    if args.version:
        print(f"Version: {SCRIPT_VERSION}")
        check_for_update_notice(force=True)
        return

    if args.check is not None:
        if args.check == "__now__":
            cmd_check_update()
        else:
            val = args.check.strip().lower()
            if val in ("true", "1", "yes", "on"):
                cmd_set_autocheck(True)
            elif val in ("false", "0", "no", "off"):
                cmd_set_autocheck(False)
            else:
                parser.error("--check expects no value, or true/false")
        return

    # No --path needed anymore -- the script just operates on wherever
    # you're standing when you run it.
    global SCRIPT_DIR
    SCRIPT_DIR = Path.cwd().resolve()

    # Passive, rate-limited check (see DEFAULTS['version_check_interval_minutes']) --
    # only prints anything if it can positively confirm a newer version
    # exists, and never blocks or errors out the command being run.
    check_for_update_notice()

    if (args.workers or args.languages or args.delay or args.show or args.hide) and not args.config:
        args.config = True

    if (args.build or args.clear) and not args.cache:
        args.cache = True

    if args.cache:
        sub_flags = [args.build, args.view, args.clear]
        if sum(bool(f) for f in sub_flags) > 1:
            parser.error("combine --cache with only one of --build, --view, or --clear at a time")
        if args.build:
            cmd_cache_build()
        elif args.view:
            cmd_cache_view()
        elif args.clear:
            cmd_cache_clear()
        else:
            cmd_cache_menu()
        return

    if args.config:
        sub_flags = [args.workers, args.languages, args.delay, args.show, args.hide, args.delete]
        if sum(bool(f) for f in sub_flags) > 1:
            parser.error("combine --config with only one of --workers, --languages, "
                         "--delay, --show, --hide, or --delete at a time")
        if args.workers:
            cmd_config_workers()
        elif args.languages:
            cmd_config_languages()
        elif args.delay:
            cmd_config_delay()
        elif args.show:
            cmd_config_show()
        elif args.hide:
            cmd_config_hide()
        elif args.delete:
             cmd_config_delete()
        else:
            cmd_config_menu()
        return

    top_flags = [
        ("create", args.create), ("update", args.update), ("add", args.add),
        ("remove", args.remove), ("delete", args.delete), ("backup", args.backup),
        ("restore", args.restore), ("view", args.view), ("cont", args.cont),
        ("upgrade", args.upgrade),
    ]
    chosen = [key for key, on in top_flags if on]
    if len(chosen) > 1:
        names = ", ".join(_MODE_FLAG_NAME.get(k, f"--{k}") for k in chosen)
        parser.error(f"choose only one mode at a time (got: {names})")

    mode = chosen[0] if chosen else None
    ask = args.ask

    if mode is None:
        mode = prompt_for_mode()
        if mode in ("create", "update", "add", "remove", "delete", "cont") and not ask:
            ask = prompt_for_ask()
        print()
        if mode == "config":
            cmd_config_menu()
            return
        if mode == "cache":
            cmd_cache_menu()
            return
        if mode == "upgrade":
            cmd_upgrade()
            return

    if mode == "upgrade":
        cmd_upgrade()
    elif mode == "create":
        cmd_create(interactive=ask)
    elif mode == "update":
        cmd_update(interactive=ask)
    elif mode == "add":
        cmd_add(interactive=ask, show_summary=args.summary)
    elif mode == "remove":
        cmd_remove(interactive=ask, show_summary=args.summary)
    elif mode == "delete":
        cmd_delete(interactive=ask)
    elif mode == "backup":
        cmd_backup()
    elif mode == "restore":
        cmd_restore()
    elif mode == "view":
        cmd_view()
    elif mode == "cont":
        cmd_continue(interactive=ask, show_summary=args.summary)


if __name__ == "__main__":
    main()