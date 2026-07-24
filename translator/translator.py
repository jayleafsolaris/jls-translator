#!/usr/bin/env python3
"""
translate.py — auto-translates `base` into every language Minecraft
Bedrock supports out of the box (including en_US), and keeps those
.lang files in sync.

`base` (no file extension) is the source-of-truth file you hand-edit.
It's kept separate from every generated .lang file — en_US.lang is
now just a regular output, an untranslated copy of `base`, exactly
like en_GB.lang.

Usage (run from anywhere — it always operates on the folder this file
lives in, e.g. RP/texts/):

    python3 translate.py --create   overwrite ALL .lang files from scratch
    python3 translate.py --update   retranslate changed keys (existing keys only)
    python3 translate.py --add      only add missing keys (no change detection)
    python3 translate.py --remove   remove keys no longer in base
    python3 translate.py --delete   delete every generated .lang file (base is kept)
    python3 translate.py --backup   zip base + all .lang files into lang_backups/
    python3 translate.py --restore  restore base + .lang files (+ cache/languages.json)
                                     from a lang_backups/ zip you pick
    python3 translate.py --view     list base + .lang files in this folder + sizes
    python3 translate.py --continue resume the last interrupted --create/--update/--add/--remove/--delete run
    python3 translate.py --cache    manage the translation cache (see below)
    python3 translate.py --config   manage script configuration (see below)

Add --ask to --create/--update/--add/--remove/--delete/--continue to be asked after each
language whether to continue or stop, e.g.:

    python3 translate.py --create --ask

Progress is saved after every completed language regardless of --ask,
so --continue can also recover from a crash, dropped connection, or force-quit.

--cache holds everything related to the translation cache used by
--update's change detection:

    python3 translate.py --cache             show the cache menu
    python3 translate.py --cache --build     rebuild the cache from the current base file...
    python3 translate.py --cache --view      show info about the cache file
    python3 translate.py --cache --clear     delete the saved progress file and the translation cache...

--config holds everything that configures how the script behaves, stored as
separate files under a .config/ folder:

    python3 translate.py --config             show the config menu
    python3 translate.py --config --workers    set the concurrent worker count
    python3 translate.py --config --languages  view/edit which are actively translated
    python3 translate.py --config --delay      set the global translation rate-limit delay
    python3 translate.py --config --delete     delete the whole config folder (resets all)
    python3 translate.py --config --show       make the config folder visible
    python3 translate.py --config --hide       make the config folder hidden

Requires:
    pip install deep_translator --user
"""

import argparse
import concurrent.futures
import hashlib
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

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

DEFAULTS = {
    "base_lang": "base",
    "cache_file": ".translate_cache.json",
    "languages_json": "languages.json",
    "backup_dir": "lang_backups",
    "progress_file": ".translate_progress.json",
    "request_delay": 0.15,   # seconds between global translation calls
    "max_retries": 3,
    "workers_min": 1,
    "workers_max": 100,
    "workers_throttle_ceiling": 20,
}

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_VERSION = "2026.07.23"

CONFIG_DIR_HIDDEN_NAME = ".config"
CONFIG_DIR_VISIBLE_NAME = "config"

# Thread-safe rate limiter variables
_RATE_LIMIT_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0
_CONFIG_DELAY = None

def config_dir_state():
    visible = SCRIPT_DIR / CONFIG_DIR_VISIBLE_NAME
    if visible.is_dir():
        return "visible", visible
    return "hidden", SCRIPT_DIR / CONFIG_DIR_HIDDEN_NAME

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
            if stripped.startswith("##"):
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
    "analyzing": "analysing", "catalog": "catalogue", "catalogs": "catalogues",
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


def get_translator(google_code):
    from deep_translator import GoogleTranslator
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

    # Group strings into batches using newlines
    for idx in valid_indices:
        text_clean = texts[idx].replace('\n', '__NL__')
        
        if current_len + len(text_clean) > MAX_BATCH_CHARS and current_batch:
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
    path = SCRIPT_DIR / DEFAULTS["cache_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_cache(base_values):
    path = SCRIPT_DIR / DEFAULTS["cache_file"]
    path.write_text(json.dumps(base_values, ensure_ascii=False, indent=2), encoding="utf-8")

def clear_cache():
    path = SCRIPT_DIR / DEFAULTS["cache_file"]
    if path.exists():
        path.unlink()
        return True
    return False

def write_languages_json():
    codes = [c for c in LANGUAGES if (SCRIPT_DIR / f"{c}.lang").exists()]
    path = SCRIPT_DIR / DEFAULTS["languages_json"]
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

    target = SCRIPT_DIR / CONFIG_DIR_VISIBLE_NAME
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

    target = SCRIPT_DIR / CONFIG_DIR_HIDDEN_NAME
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
    path = SCRIPT_DIR / DEFAULTS["progress_file"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
             return None
    return None

def save_progress(command, completed, fingerprint, elapsed_time=0.0):
    path = SCRIPT_DIR / DEFAULTS["progress_file"]
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
    path = SCRIPT_DIR / DEFAULTS["progress_file"]
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

def load_base():
    base_path = SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.exists():
        sys.exit(f"Error: base file not found (expected '{DEFAULTS['base_lang']}' in {SCRIPT_DIR})")
    return parse_lang(base_path)

def sync_en_us_from_base(base_lines):
    en_us_path = SCRIPT_DIR / "en_US.lang"
    write_lang(en_us_path, list(base_lines))
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


class SmoothProgress:
    """
    Eases a progress bar's displayed value toward the latest real ("target")
    value instead of jumping straight to it.

    translate_many() fires its progress callback whenever a parallel batch
    finishes, which -- since batches tend to land close together -- used to
    make the bar jump from e.g. 0% to 61% to 100% almost instantly instead of
    climbing steadily. A single background ticker thread now owns all
    rendering: workers just report the true progress via update(), and the
    ticker advances the displayed value toward it in small steps, closing
    the gap over roughly `catch_up_seconds` rather than in one jump. It never
    shows something less than what's actually done, and it's guaranteed to
    reach 100% (via finish()) even if real progress stalls.
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

def cmd_create(resume=False, interactive=False):
    base_lines = load_base()
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
            out_lines = list(base_lines)

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render, catch_up_seconds=3.0)
            smoother.update(key_total)
            smoother.finish()
        elif google_code == GB_CONVERT:
            out_lines = [
                line if line[0] != "entry" else ("entry", line[1], to_british(line[2]), line[3])
                for line in base_lines
            ]

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render, catch_up_seconds=3.0)
            smoother.update(key_total)
            smoother.finish()
        else:
            values = [line[2] for line in base_lines if line[0] == "entry"]

            def _render(done, _lang_idx=lang_idx, _code=code):
                _report(_lang_idx, lang_total, _code, done, key_total, start_run_time, elapsed_time)

            smoother = SmoothProgress(key_total, _render)
            effective_workers = resolve_workers(len(values))
            translated = translate_many(google_code, values, effective_workers, progress_cb=smoother.update)
            smoother.finish()

            out_lines = []
            t_idx = 0
            for line in base_lines:
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
    print(f"\nDone. Created {lang_total} language files from {DEFAULTS['base_lang']} in {format_duration(total_duration)}.")


def cmd_update(resume=False, interactive=False):
    base_lines = load_base()
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

    completed = []
    elapsed_time = 0.0

    if resume:
        progress = load_progress()
        if not progress or progress.get("command") != "update":
            print("No interrupted --update run found.\nStarting fresh.\n")
        else:
            completed = progress.get("completed", [])
            elapsed_time = progress.get("elapsed_time", 0.0)
            if progress.get("fingerprint") != fingerprint:
                print(f"Note: {DEFAULTS['base_lang']} has changed since that run was interrupted — "
                      "resuming anyway using the languages already completed.\n")
            print(f"Resuming --update: {len(completed)}/{len(existing_codes)} language(s) already checked (accumulated time: {format_duration(elapsed_time)}).\n")

    print(f"Checking {len(existing_codes)} language file(s) for changed values...\n")
    start_run_time = time.time()
    summary = []
    total_changed = 0

    for lang_idx, code in enumerate(existing_codes, start=1):
        if code in completed:
            continue
        google_code = LANGUAGES[code]
        target_path = SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)
        key_total = sum(1 for l in target_lines if l[0] == "entry")

        entries = [line for line in target_lines if line[0] == "entry"]
        to_translate_idx = [
            i for i, (_, key, current_value, _) in enumerate(entries)
            if key in base_values and (
                (key in cache and cache[key] != base_values[key])
                or (google_code is not None and current_value.strip() == "")
            )
        ]
        changed = len(to_translate_idx)
        base_done = key_total - changed
        _report(lang_idx, len(existing_codes), code, base_done, key_total, start_run_time, elapsed_time,
                note=f"({changed} to update)" if changed else "(up to date)")

        if changed and google_code == GB_CONVERT:
            texts = [base_values[entries[i][1]] for i in to_translate_idx]
            converted = [to_british(t) for t in texts]
            for i, new_value in zip(to_translate_idx, converted):
                _, key, _, inline_comment = entries[i]
                entries[i] = ("entry", key, new_value, inline_comment)

            def _render(done, _lang_idx=lang_idx, _code=code, _changed=changed, _base_done=base_done):
                _report(_lang_idx, len(existing_codes), _code, _base_done + done, key_total, start_run_time, elapsed_time,
                        note=f"({done}/{_changed} updated)")

            smoother = SmoothProgress(changed, _render, catch_up_seconds=3.0)
            smoother.update(changed)
            smoother.finish()
            _report(lang_idx, len(existing_codes), code, key_total, key_total, start_run_time, elapsed_time,
                    note=f"({changed} updated)")
        elif changed and google_code is not None:
            texts = [base_values[entries[i][1]] for i in to_translate_idx]

            def _render(done, _lang_idx=lang_idx, _code=code, _changed=changed, _base_done=base_done):
                _report(_lang_idx, len(existing_codes), _code, _base_done + done, key_total, start_run_time, elapsed_time,
                        note=f"({done}/{_changed} updated)")

            smoother = SmoothProgress(changed, _render)
            effective_workers = resolve_workers(len(texts))
            translated = translate_many(google_code, texts, effective_workers, progress_cb=smoother.update)
            smoother.finish()
            for i, new_value in zip(to_translate_idx, translated):
                _, key, _, inline_comment = entries[i]
                entries[i] = ("entry", key, new_value, inline_comment)
            _report(lang_idx, len(existing_codes), code, key_total, key_total, start_run_time, elapsed_time,
                    note=f"({changed} updated)")

        out_lines = []
        e_idx = 0
        for line in target_lines:
            if line[0] != "entry":
                out_lines.append(line)
            else:
                out_lines.append(entries[e_idx])
                e_idx += 1

        write_lang(target_path, out_lines)
        summary.append((code, changed))
        total_changed += changed

        completed.append(code)
        current_total_time = elapsed_time + (time.time() - start_run_time)
        save_progress("update", completed, fingerprint, current_total_time)

        if interactive and lang_idx < len(existing_codes) and not _ask_continue(code):
            save_cache(base_values)
            print(f"\nStopped after {code} ({len(completed)}/{len(existing_codes)} done).\n"
                  f"Total time so far: {format_duration(current_total_time)}.\n"
                  f"Run --continue to pick up where you left off.")
            return

    total_duration = elapsed_time + (time.time() - start_run_time)
    clear_progress()
    save_cache(base_values)

    if total_changed == 0:
        print(f"\nNo keys needed updating — all present .lang files already match {DEFAULTS['base_lang']} (took {format_duration(total_duration)}).")
    else:
        print(f"\nUpdate complete in {format_duration(total_duration)}:")
        for code, changed in summary:
            print(f"  {code}.lang: {changed} key(s) updated")


def cmd_add(resume=False, interactive=False):
    base_lines = load_base()
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

    print(f"Adding missing keys across {lang_total} languages...\n")
    start_run_time = time.time()
    summary = []

    for lang_idx, (code, google_code) in enumerate(all_codes, start=1):
        if code in completed:
            continue
        target_path = SCRIPT_DIR / f"{code}.lang"
        existing = entries_dict(parse_lang(target_path))

        entries = []
        missing_idx = []
        for line in base_lines:
            if line[0] != "entry":
                continue
            _, key, value, inline_comment = line
            if key in existing:
                entries.append(("entry", key, existing[key], inline_comment))
            else:
                if google_code is None:
                    placeholder = value
                elif google_code == GB_CONVERT:
                    placeholder = to_british(value)
                else:
                    placeholder = ""
                entries.append(("entry", key, placeholder, inline_comment))
                missing_idx.append(len(entries) - 1)

        added = len(missing_idx)
        base_done = key_total - added
        _report(lang_idx, lang_total, code, key_total, key_total, start_run_time, elapsed_time,
                note=f"({added} added)" if added else "")

        out_lines = []
        e_idx = 0
        for line in base_lines:
            if line[0] != "entry":
                out_lines.append(line)
            else:
                out_lines.append(entries[e_idx])
                e_idx += 1

        write_lang(target_path, out_lines)
        summary.append((code, added))

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

    print(f"\nAdd complete in {format_duration(total_duration)}:")
    for code, added in summary:
        print(f"  {code}.lang: {added} new key(s) added (untranslated -- run --update to translate)")


def cmd_continue(interactive=False):
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
        cmd_add(resume=True, interactive=interactive)
    elif command == "remove":
        cmd_remove(resume=True, interactive=interactive)
    elif command == "delete":
        cmd_delete(resume=True, interactive=interactive)
    else:
        print("Saved progress is unrecognized or corrupted.\n"
              "Re-run --create, --update, --add, --remove, or --delete to start over.")


def cmd_remove(resume=False, interactive=False):
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

    print(f"Checking {len(existing_codes)} language file(s) for deprecated keys...\n")
    start_run_time = time.time()
    summary = []
    total_removed = 0

    for lang_idx, code in enumerate(existing_codes, start=1):
        if code in completed:
            continue

        target_path = SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)
        key_total = sum(1 for l in target_lines if l[0] == "entry")

        removed = 0
        out_lines = []
        key_idx = 0
        _report(lang_idx, len(existing_codes), code, 0, key_total, start_run_time, elapsed_time)
        for line in target_lines:
            if line[0] != "entry":
                out_lines.append(line)
                continue
            _, key, value, inline_comment = line
            key_idx += 1

            if key not in base_values:
                removed += 1
                _report(lang_idx, len(existing_codes), code, key_idx, key_total, start_run_time, elapsed_time, note=f"({removed} removed)")
                continue

            out_lines.append(line)
            note = f"({removed} removed)" if removed else "(clean)"
            _report(lang_idx, len(existing_codes), code, key_idx, key_total, start_run_time, elapsed_time, note=note)

        write_lang(target_path, out_lines)
        summary.append((code, removed))
        total_removed += removed

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
    trimmed_cache = {k: v for k, v in cache.items() if k in base_values}
    if trimmed_cache != cache:
        save_cache(trimmed_cache)

    if total_removed == 0:
        print(f"\nNo deprecated keys found — all present .lang files already match {DEFAULTS['base_lang']}'s keys (took {format_duration(total_duration)}).")
    else:
        print(f"\nCleanup complete in {format_duration(total_duration)}:")
        for code, removed in summary:
            print(f"  {code}.lang: {removed} key(s) removed")


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


def cmd_publish():
    source = SCRIPT_PATH
    target = source.parent / "translator"
    base_path = SCRIPT_DIR / DEFAULTS["base_lang"]
    base_exists = base_path.exists()

    if source.resolve() == target.resolve():
        print(f"{source.name} is already published under its final name -- "
              f"there's no separate source file left to copy.")
        print(f"This will completely delete {source.name}"
              + (f" and {base_path.name}" if base_exists else "")
              + ", with nothing left behind.")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return
        source.unlink()
        if base_exists:
            base_path.unlink()
        print(f"\nDone. {source.name}"
              + (f" and {base_path.name}" if base_exists else "")
              + " have been completely deleted.")
        return

    print(f"This will:")
    print(f"  1. Copy {source.name} to {target.name} (a fully working duplicate)")
    print(f"  2. Delete {source.name} itself")
    if base_exists:
        print(f"  3. Delete {base_path.name}")
    print(f"\nAfterward only {target.name} will run.\n{source.name}"
          + (f" and {base_path.name} will" if base_exists else " will")
          + " be deleted.")
    confirm = input("Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    if target.exists():
        overwrite = input(f"{target.name} already exists here. Overwrite it? [y/N]: ").strip().lower()
        if overwrite not in ("y", "yes"):
            print("Cancelled.")
            return

    shutil.copy2(source, target)
    source.unlink()
    if base_exists:
        base_path.unlink()

    print(f"\nDone. {target.name} is now the working copy (run it with `python3 {target.name}`).")
    print(f"{source.name}" + (f" and {base_path.name} have" if base_exists else " has") + " been deleted.")


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
        cache_path = SCRIPT_DIR / DEFAULTS["cache_file"]
        if cache_path.exists():
            zf.write(cache_path, arcname=cache_path.name)
        lj_path = SCRIPT_DIR / DEFAULTS["languages_json"]
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
        zf.extractall(SCRIPT_DIR)

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


def cmd_cache_build():
    base_lines = load_base()
    base_values = entries_dict(base_lines)
    save_cache(base_values)
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


def cmd_cache_view():
    path = SCRIPT_DIR / DEFAULTS["cache_file"]
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
    parser.add_argument("--publish", action="store_true",
                         help="copy this script to 'translator' (no extension), then delete "
                              "this file itself")
    parser.add_argument("--version", action="store_true", help="print the script version and exit")
    parser.add_argument("--ask", action="store_true",
                         help="ask after each item whether to continue or stop "
                              "(combine with --create/--update/--add/--remove/--delete/--continue)")
    args = parser.parse_args()

    if args.version:
        print(f"translate.py version {SCRIPT_VERSION}")
        return

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
        ("publish", args.publish),
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

    if mode == "create":
        cmd_create(interactive=ask)
    elif mode == "update":
        cmd_update(interactive=ask)
    elif mode == "add":
        cmd_add(interactive=ask)
    elif mode == "remove":
        cmd_remove(interactive=ask)
    elif mode == "delete":
        cmd_delete(interactive=ask)
    elif mode == "backup":
        cmd_backup()
    elif mode == "restore":
        cmd_restore()
    elif mode == "view":
        cmd_view()
    elif mode == "cont":
        cmd_continue(interactive=ask)
    elif mode == "publish":
        cmd_publish()


if __name__ == "__main__":
    main()
