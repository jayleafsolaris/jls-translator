"""--compile: obfuscate base's raw text with a fresh random key each run."""

from ..common import state
from ..common.state import DEFAULTS
from ..common.obfuscate import compile_text, is_compiled


def cmd_compile():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.is_file():
        print(f"No '{DEFAULTS['base_lang']}' file found -- nothing to compile.")
        return

    text = base_path.read_text(encoding="utf-8")
    if is_compiled(text):
        print(f"'{DEFAULTS['base_lang']}' is already compiled -- run --decompile first.")
        return

    base_path.write_text(compile_text(text), encoding="utf-8")
    print("Done! Base: Compiled")