"""--restore: restore base + .lang files (+ cache/languages.json) from a lang_backups/ zip."""

import shutil
import zipfile

from ..common import state
from ..common.state import DEFAULTS, PACKAGE_DIR
from ..common.progress import _human_size

def cmd_restore():
    backup_dir = state.SCRIPT_DIR / DEFAULTS["backup_dir"]
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
        for name in zf.namelist():
            if name in (DEFAULTS["cache_file"], DEFAULTS["languages_json"]):
                dest_dir = PACKAGE_DIR
            else:
                dest_dir = state.SCRIPT_DIR
            with zf.open(name) as src, open(dest_dir / name, "wb") as dst:
                shutil.copyfileobj(src, dst)

    print(f"\nRestored {len(names)} file(s) from {chosen.name}.")
