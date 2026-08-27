"""--compile: obfuscate base's raw text with a fresh random key each run."""

from ..common import state
from ..common.state import DEFAULTS
from ..common.obfuscate import compile_text, is_compiled
from ..common.cache import save_compile_key


def cmd_compile():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.is_file():
        print(f"No '{DEFAULTS['base_lang']}' file found -- nothing to compile.")
        return

    text = base_path.read_text(encoding="utf-8")
    if is_compiled(text):
        print(f"'{DEFAULTS['base_lang']}' is already compiled -- run --decompile first.")
        return

    compiled, key = compile_text(text)
    base_path.write_text(compiled, encoding="utf-8")
    save_compile_key(key)
    print("Done! Base: Compiled")