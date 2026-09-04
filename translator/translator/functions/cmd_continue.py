from ..common.progress import load_progress
from ..modes.add import cmd_add
from ..modes.create import cmd_create
from ..modes.delete import cmd_delete
from ..modes.remove import cmd_remove
from ..modes.update import cmd_update


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
