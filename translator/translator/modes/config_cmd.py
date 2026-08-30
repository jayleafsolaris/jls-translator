"""
--config and its subcommands: worker count, delay, active languages,
and hiding/showing/deleting the config folder.
"""

import os
import shutil
import sys

from ..common import state, config_store
from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME
from ..common.config_store import load_config_value, save_config_value, config_dir_state
from ..common.cache import compute_auto_workers, get_active_language_codes, save_active_language_codes

def cmd_config_workers():
    current = load_config_value("workers", default="auto")
    auto_now = compute_auto_workers()

    print(f"Current setting: {current}" + (f" (resolves to {auto_now} right now)" if current == "auto" else ""))
    print(f"\nEnter a number from {DEFAULTS['workers_min']}-{DEFAULTS['workers_max']}, or 'auto' "
          f"to let the script pick based on your CPU and each run's size.")
    print("Higher values translate faster but use more CPU/RAM for the local model at once.\n")

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
                f"{n} workers is high and may saturate your CPU translating locally.\n"
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
            marker = "I" if code in selected else "O"
            name = LANGUAGE_NAMES.get(code, "")
            print(f"  {i:>2}. [{marker}] {code:<8} {name}")
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
    elif key == "show":
        cmd_config_show()
    elif key == "hide":
        cmd_config_hide()
    elif key == "delete":
        cmd_config_delete()

