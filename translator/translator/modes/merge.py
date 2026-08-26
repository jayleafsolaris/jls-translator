"""--merge: rebuild base from the folder hierarchy created by --split."""

from ..common import state
from ..common.state import DEFAULTS
from ..common.sections import load_section_order, render_sections


def cmd_merge():
    order = load_section_order()
    if not order:
        print("No section-order cache found -- run --split first, or there's nothing to merge.")
        return

    missing = [n for n in order if not (state.SCRIPT_DIR / n / f"{n}.txt").exists()]
    if missing:
        print("Missing expected section file(s), aborting:")
        for n in missing:
            print(f"  {n}/{n}.txt")
        return

    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if base_path.exists():
        print(f"'{DEFAULTS['base_lang']}' already exists and will be overwritten.")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

    sections = []
    for name in order:
        content = (state.SCRIPT_DIR / name / f"{name}.txt").read_text(encoding="utf-8")
        sections.append((name, content))

    base_path.write_text(render_sections(sections), encoding="utf-8")

    for name in order:
        folder = state.SCRIPT_DIR / name
        txt = folder / f"{name}.txt"
        if txt.exists():
            txt.unlink()
        try:
            folder.rmdir()
        except OSError:
            pass  # folder has other stuff in it -- leave it, don't delete anything unexpected

    print(f"Merged {len(order)} folder(s) back into '{DEFAULTS['base_lang']}'.")