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
    jls-translator --upgrade --enforce
                              force the upgrade even if already on the latest version,
                                     or if the remote version can't be determined
    jls-translator --check    manually check GitHub for a newer version right now
                                     (doesn't change automatic checking)
    jls-translator --check true|false
                              turn the automatic passive update check (the one that
                                     runs quietly on every command) on or off
    jls-translator --usage   show current hourly/daily translation usage percentages
                                     and when each resets (no --path needed)
    jls-translator --usage --live <minutes>
                              live-redraw the usage/reset countdown every 100ms for
                                     the given number of minutes instead of one snapshot
    jls-translator --debug   alone: reset __debug-log.json (in this folder) to a
                                     clean empty state. Combine with --create/--update/
                                     --add/--remove/--continue/etc to print + log a
                                     timestamped (:hh:mm:ss:) line for every notable
                                     translation step -- useful for pinning down exactly
                                     where a run that looks frozen actually stopped
    jls-translator --push    push <cwd>/jls-translator/ up to this tool's own GitHub
                                     repo as one combined commit (branch: --release)
    jls-translator --push --clean
                              push plain, uncompiled source instead of obfuscating it --
                                     primarily for testing
    jls-translator --pull    pull that repo down into <cwd>/jls-translator/, mirroring
                                     it exactly (adds/updates/removes files in that folder only)
    jls-translator --token   view, set, or remove the GitHub token --push/--pull use
    jls-translator --token <TOKEN>
                              store that as the GitHub personal access token
    jls-translator --token remove
                              delete the stored GitHub token

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

--push/--pull sync <cwd>/jls-translator/ (a folder named after this tool's
own repo, GITHUB_REPO in state.py) specifically -- NOT the rest of the
current directory -- against wherever this package's cli.py lives in this
tool's own repo, on whichever branch --release currently points to. Keeping
this confined to its own subfolder means it can never touch base, your
.lang files, or anything else already sitting in a project folder. The
remote location isn't assumed to be named any particular thing -- both scan
the repo's tree for wherever cli.py actually sits, the same way --upgrade
does. --push diffs against the remote tree (by content, not by timestamp)
and makes one combined commit for everything changed/removed; --pull
mirrors the remote back down into that same subfolder. Your local cache,
config folder, and stored GitHub token are never pushed and never touched
by --pull's mirroring, no matter what. Both need a GitHub token with write
access (for --push) set via --token first -- if the token is missing or
lacks access, both fail with a plain "You are not authorized to do this"
rather than a stack trace.

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
from .common.state import SCRIPT_VERSION, DEFAULTS
from .functions._extract_code_compile_key import _extract_code_compile_key

state._CODE_COMPILE_KEY = _extract_code_compile_key(Path(__file__).read_text(encoding="utf-8"))
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
from .modes.usage_cmd import cmd_usage
from .modes.push import cmd_push
from .modes.pull import cmd_pull
from .modes.token import cmd_show_token, cmd_set_token, cmd_remove_token
from .modes.debug import cmd_debug
from .common import debug_log
from .common.base_backup import refresh_base_backup, load_base_backup
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
    ("push", "Push cwd/jls-translator/ up to GitHub as one combined commit"),
    ("pull", "Pull GitHub down into cwd/jls-translator/, mirroring it exactly"),
    ("cont", "Resume the last interrupted run (any modifying command)"),
    ("cache", "Manage the translation cache (build, view, or clear)"),
    ("config", "Manage script configuration (workers, active languages, delay)"),
    ("upgrade", "Update the script to the latest version from GitHub"),
]
_MODE_FLAG_NAME = {"cont": "--continue"}
if __name__ == "__main__":
    main()
from .functions.main import main
from .functions.prompt_for_ask import prompt_for_ask
from .functions.prompt_for_mode import prompt_for_mode
##d967ce2538f6a0557fefb33b1:919f35f986990deb115e4250826850cdc08afa68b5a72adca04518ac8ca801a4
