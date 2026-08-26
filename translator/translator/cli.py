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
    jls-translator --split    split base into a folder hierarchy along its ## sections
    jls-translator --merge    merge that folder hierarchy back into base
    jls-translator --compile   obfuscate base with a fresh random key (only touches base)
    jls-translator --decompile reverse --compile using the key stored in base
    jls-translator --continue resume the last interrupted --create/--update/--add/--remove/--delete run
    jls-translator --cache    manage the translation cache (see below)
    jls-translator --config   manage script configuration (see below)
    jls-translator --release  view or set which GitHub branch --upgrade downloads
                                     from and the update checker compares against
    jls-translator --release <branch>
                              set the release branch (persisted; --release alone shows it)
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

--split and --merge are one-off commands (no --ask/--continue/--summary):

    jls-translator --split    turns each '## Name' section of base into
                                     Name/Name.txt, deletes base, and caches the
                                     section order for --merge to use later
    jls-translator --merge    reads that cached order back and reassembles
                                     base from the Name/Name.txt files, then
                                     removes the section folders

--backup includes any current --split section folders automatically; --restore
puts them back where they came from.

--compile and --decompile are also one-off and only ever touch `base` itself
(no other files). --compile scrambles base with a brand-new random key every
time it runs, appending that key as a marker line at the bottom of the file
so --decompile can reverse it exactly.

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
import sys
from pathlib import Path

from .common import state
from .common.state import SCRIPT_VERSION
from .common.netcheck import check_for_update_notice, cmd_check_update, cmd_set_autocheck
from .modes.config_cmd import (
    cmd_config_workers, cmd_config_languages, cmd_config_delay,
    cmd_config_show, cmd_config_hide, cmd_config_delete, cmd_config_menu,
)
from .modes.cache_cmd import cmd_cache_build, cmd_cache_view, cmd_cache_clear, cmd_cache_menu
from .modes.create import cmd_create
from .modes.update import cmd_update
from .modes.add import cmd_add
from .modes.remove import cmd_remove
from .modes.delete import cmd_delete
from .modes.backup import cmd_backup
from .modes.restore import cmd_restore
from .modes.view import cmd_view
from .modes.split import cmd_split
from .modes.merge import cmd_merge
from .modes.compile import cmd_compile
from .modes.decompile import cmd_decompile
from .modes.cont import cmd_continue
from .modes.upgrade import cmd_upgrade
from .modes.release import cmd_show_release_branch, cmd_set_release_branch

_MODES = [
    ("create", "Overwrite ALL .lang files from scratch"),
    ("update", "Retranslate changed keys (existing keys only)"),
    ("add", "Only add missing keys (no change detection)"),
    ("remove", "Remove keys no longer in base"),
    ("delete", "Delete every generated .lang file (base is kept)"),
    ("backup", "Zip all .lang files into lang_backups/"),
    ("restore", "Restore .lang files from a lang_backups/ zip"),
    ("view", "List .lang files in this folder + sizes"),
    ("split", "Split base into a folder hierarchy along its ## sections"),
    ("merge", "Merge that folder hierarchy back into base"),
    ("compile", "Obfuscate base with a fresh random key"),
    ("decompile", "Reverse --compile using the key stored in base"),
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
    parser.add_argument("--split", action="store_true",
                         help="split base into a folder hierarchy along its '## Name' sections "
                              "(one-off; base is deleted and replaced by the folders)")
    parser.add_argument("--merge", action="store_true",
                         help="merge a --split folder hierarchy back into base, using the "
                              "cached section order (one-off)")
    parser.add_argument("--compile", action="store_true",
                         help="obfuscate base with a fresh random key (one-off, only touches base)")
    parser.add_argument("--decompile", action="store_true",
                         help="reverse --compile using the key stored in base (one-off, only touches base)")
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
    parser.add_argument("--release", nargs="?", const="__show__", default=None, metavar="BRANCH",
                         help="with no value: show which GitHub branch --upgrade downloads from "
                              "and the update checker compares against. "
                              "with a branch name: set that as the release branch (persisted "
                              "until changed again)")
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

    if args.release is not None:
        if args.release == "__show__":
            cmd_show_release_branch()
        else:
            cmd_set_release_branch(args.release)
        return

    # No --path needed anymore -- the script just operates on wherever
    # you're standing when you run it.
    state.SCRIPT_DIR = Path.cwd().resolve()

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
        ("restore", args.restore), ("view", args.view), ("split", args.split),
        ("merge", args.merge), ("compile", args.compile), ("decompile", args.decompile),
        ("cont", args.cont), ("upgrade", args.upgrade),
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
    elif mode == "split":
        cmd_split()
    elif mode == "merge":
        cmd_merge()
    elif mode == "compile":
        cmd_compile()
    elif mode == "decompile":
        cmd_decompile()
    elif mode == "cont":
        cmd_continue(interactive=ask, show_summary=args.summary)


if __name__ == "__main__":
    main()