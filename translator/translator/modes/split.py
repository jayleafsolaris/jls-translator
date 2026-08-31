"""--split: turn base into a base/ folder hierarchy mirroring every heading depth."""

from ..common import state
from ..common.state import DEFAULTS
from ..common.sections import (
    parse_tree, find_duplicate_siblings, write_tree, save_section_data,
)


def cmd_split():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.is_file():
        print(f"No '{DEFAULTS['base_lang']}' file found -- nothing to split.")
        return

    text = base_path.read_text(encoding="utf-8")
    try:
        root, markers = parse_tree(text)
    except ValueError as e:
        print(f"Can't split: {e}")
        return

    if not root.children:
        print(f"No '##' headings found in '{DEFAULTS['base_lang']}' -- nothing to split.")
        return

    dupes = find_duplicate_siblings(root)
    if dupes:
        print("Can't split: sibling heading(s) collide on the same folder name:")
        for d in dupes:
            print(f"  {d}")
        return

    base_path.unlink()
    base_dir = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    base_dir.mkdir(parents=True, exist_ok=True)
    for child in root.children:
        write_tree(child, base_dir / child.folder)

    save_section_data(root.children, markers)
    print("Done! Base: Split")