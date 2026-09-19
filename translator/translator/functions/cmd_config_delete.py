from ..common.config_store import load_config_value, save_config_value, get_request_delay, config_dir_state
import shutil


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
