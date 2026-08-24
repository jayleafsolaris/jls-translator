"""--backup: zip base + all .lang files (+ cache/languages.json) into lang_backups/."""

import zipfile
from datetime import datetime

from ..common import state
from ..common.state import DEFAULTS, PACKAGE_DIR

def cmd_backup():
    backup_dir = state.SCRIPT_DIR / DEFAULTS["backup_dir"]
    backup_dir.mkdir(exist_ok=True)

    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    lang_files = sorted(state.SCRIPT_DIR.glob("*.lang"))
    all_files = ([base_path] if base_path.exists() else []) + lang_files
    if not all_files:
        print(f"No {DEFAULTS['base_lang']} or .lang files found to back up.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"lang_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in all_files:
            zf.write(p, arcname=p.name)
        cache_path = PACKAGE_DIR / DEFAULTS["cache_file"]
        if cache_path.exists():
            zf.write(cache_path, arcname=cache_path.name)
        lj_path = PACKAGE_DIR / DEFAULTS["languages_json"]
        if lj_path.exists():
             zf.write(lj_path, arcname=lj_path.name)

    print(f"Backed up {len(all_files)} file(s) (including {DEFAULTS['base_lang']}) to {zip_path.relative_to(state.SCRIPT_DIR)}")
