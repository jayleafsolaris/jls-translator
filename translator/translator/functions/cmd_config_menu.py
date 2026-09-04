from ..common import state, config_store
from ..common.config_store import load_config_value, save_config_value, get_request_delay, config_dir_state
from .cmd_config_delay import cmd_config_delay
from .cmd_config_delete import cmd_config_delete
from .cmd_config_hide import cmd_config_hide
from .cmd_config_languages import cmd_config_languages
from .cmd_config_show import cmd_config_show
from .cmd_config_workers import cmd_config_workers


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
