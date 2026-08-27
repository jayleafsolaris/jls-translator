"""--decompile: reverse --compile using the key stored in base's trailing marker line."""

from ..common import state
from ..common.state import DEFAULTS
from ..common.obfuscate import decompile_text


def cmd_decompile():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.is_file():
        print(f"No '{DEFAULTS['base_lang']}' file found -- nothing to decompile.")
        return

    text = base_path.read_text(encoding="utf-8")
    try:
        original = decompile_text(text)
    except ValueError as e:
        print(f"Can't decompile: {e}")
        return

    base_path.write_text(original, encoding="utf-8")
    print("Done! Base: Decompiled")