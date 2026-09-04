from ..common import state
from ..common.state import DEFAULTS, PACKAGE_DIR
from datetime import datetime
import zipfile


def cmd_backup():
    backup_dir = state.SCRIPT_DIR / DEFAULTS["backup_dir"]
    backup_dir.mkdir(exist_ok=True)

    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    lang_files = sorted(state.SCRIPT_DIR.glob("*.lang"))

    # base is either a plain file, or (after --split) a base/ folder full of
    # nested heading folders + keys.txt files -- walk it directly rather
    # than relying on the section-tree cache, so backup always reflects
    # whatever's actually on disk right now.
    base_entries = []  # list of (source_path, arcname)
    if base_path.is_file():
        base_entries.append((base_path, base_path.name))
    elif base_path.is_dir():
        for f in sorted(base_path.rglob("*")):
            if f.is_file():
                base_entries.append((f, str(f.relative_to(state.SCRIPT_DIR))))

    if not base_entries and not lang_files:
        print(f"No {DEFAULTS['base_lang']}, .lang files, or split '{DEFAULTS['base_lang']}/' folder found to back up.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"lang_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p, arcname in base_entries:
            zf.write(p, arcname=arcname)
        for p in lang_files:
            zf.write(p, arcname=p.name)
        cache_path = PACKAGE_DIR / DEFAULTS["cache_file"]
        if cache_path.exists():
            zf.write(cache_path, arcname=cache_path.name)
        lj_path = PACKAGE_DIR / DEFAULTS["languages_json"]
        if lj_path.exists():
             zf.write(lj_path, arcname=lj_path.name)
        # Only worth restoring alongside a split base/ folder -- without
        # that folder the cache has nothing to reconstruct.
        so_path = PACKAGE_DIR / DEFAULTS["section_order_cache"]
        if so_path.exists() and base_path.is_dir():
            zf.write(so_path, arcname=so_path.name)

    total = len(base_entries) + len(lang_files)
    note = f" (including {DEFAULTS['base_lang']})" if base_entries else ""
    print(f"Backed up {total} file(s){note} to {zip_path.relative_to(state.SCRIPT_DIR)}")
