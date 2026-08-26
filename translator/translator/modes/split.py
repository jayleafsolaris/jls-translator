"""--split: split base into a folder hierarchy based on its ## sections."""

from ..common import state
from ..common.state import DEFAULTS
from ..common.sections import parse_sections, sanitize_name, save_section_order


def cmd_split():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.exists():
        print(f"No '{DEFAULTS['base_lang']}' file found -- nothing to split.")
        return

    text = base_path.read_text(encoding="utf-8")
    try:
        sections = parse_sections(text)
    except ValueError as e:
        print(f"Can't split: {e}")
        return

    if not sections:
        print(f"No '##' sections found in '{DEFAULTS['base_lang']}' -- nothing to split.")
        return

    names = [sanitize_name(name) for name, _ in sections]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        print(f"Can't split: duplicate section name(s) after sanitizing: {', '.join(dupes)}")
        return

    print(f"This will delete '{DEFAULTS['base_lang']}' and replace it with {len(names)} folder(s):")
    for n in names:
        exists_note = "  (already exists, will be overwritten)" if (state.SCRIPT_DIR / n).exists() else ""
        print(f"  {n}/{n}.txt{exists_note}")
    confirm = input("Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    for name, content in sections:
        folder_name = sanitize_name(name)
        folder = state.SCRIPT_DIR / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{folder_name}.txt").write_text(content, encoding="utf-8")

    save_section_order(names)
    base_path.unlink()

    print(f"Split '{DEFAULTS['base_lang']}' into {len(names)} folder(s): {', '.join(names)}")
