"""--merge: rebuild base from the base/ folder hierarchy created by --split."""

import shutil

from ..common import state
from ..common.state import DEFAULTS
from ..common.sections import load_section_tree, render_tree


def cmd_merge():
    tree = load_section_tree()
    if not tree:
        print("No section-tree cache found -- run --split first, or there's nothing to merge.")
        return

    base_dir = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_dir.is_dir():
        print(f"No '{DEFAULTS['base_lang']}/' folder found -- nothing to merge.")
        return

    rendered = render_tree(tree, base_dir)

    shutil.rmtree(base_dir)
    (state.SCRIPT_DIR / DEFAULTS["base_lang"]).write_text(rendered, encoding="utf-8")

    print("Done! Base: merged")