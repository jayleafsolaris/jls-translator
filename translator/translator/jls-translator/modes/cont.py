"""--continue: resume the last interrupted create/update/add/remove/delete run."""

from ..common.progress import load_progress
from .create import cmd_create
from .update import cmd_update
from .add import cmd_add
from .remove import cmd_remove
from .delete import cmd_delete

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
