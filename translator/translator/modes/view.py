"""--view: list base + .lang files in this folder, with sizes and key counts."""

from ..common import state
from ..common.state import DEFAULTS
from ..common.lang_io import parse_lang, entries_dict
from ..common.progress import _human_size
from ..common.cache import get_update_count

def cmd_view():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    files = ([base_path] if base_path.exists() else []) + sorted(state.SCRIPT_DIR.glob("*.lang"))
    if not files:
        print(f"No {DEFAULTS['base_lang']} or .lang files found in this directory.")
        return

    print(f"{'File':<16}{'Size':>10}   Keys")
    print("-" * 40)
    for p in files:
         size = p.stat().st_size
         key_count = len(entries_dict(parse_lang(p)))
         marker = " (base)" if p.name == DEFAULTS["base_lang"] else ""
         print(f"{p.name:<16}{_human_size(size):>10}   {key_count}{marker}")
    if base_path.exists():
        count = get_update_count()
        print(f"\n--update count for this base file: {count}/{DEFAULTS['update_limit']}")

