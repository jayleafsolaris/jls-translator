from ..common import state, config_store
from ..common.cache import compute_auto_workers, get_active_language_codes, save_active_language_codes
from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME
from ._curses_available import _curses_available
from ._edit_active_languages_curses import _edit_active_languages_curses
from ._edit_active_languages_text import _edit_active_languages_text


def cmd_config_languages():
    codes = list(LANGUAGES.keys())
    active = set(get_active_language_codes())

    print(f"{len(active)}/{len(codes)} language(s) active (translated by --create/--update/--add):\n")
    for code in codes:
        marker = "I" if code in active else "O"
        exists = (state.SCRIPT_DIR / f"{code}.lang").exists()
        file_note = "file exists" if exists else "not created yet"
        name = LANGUAGE_NAMES.get(code, "")
        print(f"  [{marker}] {code:<8} {name:<24} ({file_note})")

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

    stale = [c for c in codes if c not in result and (state.SCRIPT_DIR / f"{c}.lang").exists()]
    if stale:
        print("Note: these .lang files already exist but won't be touched by "
              "--create/--update/--add while inactive (still on disk):")
        for c in stale:
            print(f"  {c}.lang")
