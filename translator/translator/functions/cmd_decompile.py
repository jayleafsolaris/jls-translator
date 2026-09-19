from ..common import state
from ..common.cache import load_compile_key, clear_compile_key
from ..common.obfuscate import decompile_text
from ..common.state import DEFAULTS


def cmd_decompile():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.is_file():
        print(f"No '{DEFAULTS['base_lang']}' file found -- nothing to decompile.")
        return

    key = load_compile_key()
    if key is None:
        print("No cached compile key found -- can't decompile.")
        return

    text = base_path.read_text(encoding="utf-8")
    try:
        original = decompile_text(text, key)
    except ValueError as e:
        print(f"Can't decompile: {e}")
        return

    base_path.write_text(original, encoding="utf-8")
    clear_compile_key()
    print("Done! Base: Decompiled")
