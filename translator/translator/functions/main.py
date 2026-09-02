from ..common import debug_log
from ..common import state
from ..common.base_backup import refresh_base_backup, load_base_backup
from ..common.netcheck import check_for_update_notice, cmd_check_update, cmd_set_autocheck
from ..common.state import SCRIPT_VERSION, DEFAULTS
from ..modes.add import cmd_add
from ..modes.backup import cmd_backup
from ..modes.cache_cmd import cmd_cache_build, cmd_cache_view, cmd_cache_clear, cmd_cache_menu
from ..modes.compile import cmd_compile
from ..modes.config_cmd import cmd_config_workers, cmd_config_languages, cmd_config_delay, cmd_config_show, cmd_config_hide, cmd_config_delete, cmd_config_menu
from ..modes.cont import cmd_continue
from ..modes.create import cmd_create
from ..modes.debug import cmd_debug
from ..modes.decompile import cmd_decompile
from ..modes.delete import cmd_delete
from ..modes.merge import cmd_merge
from ..modes.pull import cmd_pull
from ..modes.push import cmd_push
from ..modes.release import cmd_show_release_branch, cmd_set_release_branch
from ..modes.remove import cmd_remove
from ..modes.restore import cmd_restore
from ..modes.split import cmd_split
from ..modes.token import cmd_show_token, cmd_set_token, cmd_remove_token
from ..modes.update import cmd_update
from ..modes.upgrade import cmd_upgrade
from ..modes.usage_cmd import cmd_usage
from ..modes.view import cmd_view
from pathlib import Path
import argparse
from ..cli import _MODE_FLAG_NAME
from .prompt_for_ask import prompt_for_ask
from .prompt_for_mode import prompt_for_mode


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
    parser.add_argument("--usage", action="store_true",
                         help="show current hourly/daily translation usage percentages and reset times")
    parser.add_argument("--debug", action="store_true",
                         help="alone: reset __debug-log.json (in the current project folder) to a "
                              "clean empty state. combined with --create/--update/--add/--remove/"
                              "--continue/etc: print + log a timestamped (:hh:mm:ss:) line for every "
                              "notable translation step, useful for pinning down exactly where a "
                              "run that looks frozen actually stopped")
    parser.add_argument("--cooldown", dest="cooldown_hours", type=float, metavar="HOURS",
                         help="use with --usage to manually force a translation cooldown, "
                              "1-72 hours (clamped to that range)")
    parser.add_argument("--live", dest="live_minutes", type=float, metavar="MINUTES",
                         help="use with --usage to redraw the usage/reset countdown in place "
                              "every 100ms for the given number of minutes, instead of a single "
                              "static snapshot")
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
    parser.add_argument("--enforce", action="store_true",
                         help="use with --upgrade to force it even if already on the latest "
                              "version, or if the remote version can't be determined")
    parser.add_argument("--summary", action="store_true", help="show detailed per-language results for --add and --remove")
    parser.add_argument("--push", action="store_true",
                         help="push <cwd>/jls-translator/ up to this tool's own GitHub repo "
                              "as one combined commit (branch: --release)")
    parser.add_argument("--pull", action="store_true",
                         help="pull <cwd>/jls-translator/ down from that repo, mirroring it exactly")
    parser.add_argument("--token", nargs="?", const="__show__", default=None, metavar="TOKEN",
                         help="with no value: show whether a GitHub token is stored. "
                              "with a value: store that as the token --push/--pull use. "
                              "with 'remove': delete the stored token")
    
    args = parser.parse_args()

    if args.version:
        print(f"Version: {SCRIPT_VERSION}")
        check_for_update_notice(force=True)
        return

    if args.usage:
        cmd_usage(cooldown_hours=args.cooldown_hours, live_minutes=args.live_minutes)
        return

    if args.cooldown_hours is not None:
        print("--cooldown only has an effect combined with --usage, e.g. --usage --cooldown 6")
        return

    if args.live_minutes is not None:
        print("--live only has an effect combined with --usage, e.g. --usage --live 2")
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

    if args.token is not None:
        if args.token == "__show__":
            cmd_show_token()
        elif args.token.strip().lower() == "remove":
            cmd_remove_token()
        else:
            cmd_set_token(args.token)
        return

    # No --path needed anymore -- the script just operates on wherever
    # you're standing when you run it.
    state.SCRIPT_DIR = Path.cwd().resolve()

    # --debug with no other mode: standalone log-reset command, not a
    # translation run -- see modes/debug.py.
    if args.debug and not any([
        args.create, args.update, args.add, args.remove, args.delete,
        args.backup, args.restore, args.view, args.split, args.merge,
        args.compile, args.decompile, args.cont, args.cache, args.config,
        args.push, args.pull, args.upgrade,
    ]):
        cmd_debug()
        return

    if args.debug:
        debug_log.enable()

    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.exists():
        cached = load_base_backup()
        if cached is not None:
            print("The base file could not be found. Do you want to restore it?")
            answer = input("[y/N]: ").strip().lower()
            if answer in ("y", "yes"):
                base_path.write_text(cached, encoding="utf-8")
                print(f"Restored '{DEFAULTS['base_lang']}' from backup.")
    else:
        refresh_base_backup(state.SCRIPT_DIR)

    try:
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
            ("push", args.push), ("pull", args.pull),
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
                cmd_upgrade(enforce=args.enforce)
                return

        if mode == "upgrade":
            cmd_upgrade(enforce=args.enforce)
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
        elif mode == "push":
            cmd_push()
        elif mode == "pull":
            cmd_pull()
        elif mode == "cont":
            cmd_continue(interactive=ask, show_summary=args.summary)
    finally:
        refresh_base_backup(state.SCRIPT_DIR)
