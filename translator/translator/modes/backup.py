"""--backup: zip base + all .lang files (+ split section folders + cache/languages.json) into lang_backups/."""

import zipfile
from datetime import datetime

from ..common import state
from ..common.state import DEFAULTS, PACKAGE_DIR
from ..common.sections import load_section_order

def cmd_backup():
    backup_dir = state.SCRIPT_DIR / DEFAULTS["backup_dir"]
    backup_dir.mkdir(exist_ok=True)

    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    lang_files = sorted(state.SCRIPT_DIR.glob("*.lang"))
    all_files = ([base_path] if base_path.exists() else []) + lang_files

    # If the project is currently in split form (base replaced by section
    # folders), back those up too -- using the cached order rather than
    # guessing which top-level folders belong to us, so unrelated project
    # folders never end up in the zip.
    order = load_section_order()
    section_files = []
    if order:
        for name in order:
            txt = state.SCRIPT_DIR / name / f"{name}.txt"
            if txt.exists():
                section_files.append((name, txt))

    if not all_files and not section_files:
        print(f"No {DEFAULTS['base_lang']}, .lang files, or split section folders found to back up.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"lang_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in all_files:
            zf.write(p, arcname=p.name)
        for name, p in section_files:
            zf.write(p, arcname=f"{name}/{p.name}")
        cache_path = PACKAGE_DIR / DEFAULTS["cache_file"]
        if cache_path.exists():
            zf.write(cache_path, arcname=cache_path.name)
        lj_path = PACKAGE_DIR / DEFAULTS["languages_json"]
        if lj_path.exists():
             zf.write(lj_path, arcname=lj_path.name)
        so_path = PACKAGE_DIR / DEFAULTS["section_order_cache"]
        if so_path.exists() and section_files:
            zf.write(so_path, arcname=so_path.name)

    total = len(all_files) + len(section_files)
    note = f" (including {DEFAULTS['base_lang']})" if base_path.exists() else ""
    print(f"Backed up {total} file(s){note} to {zip_path.relative_to(state.SCRIPT_DIR)}")