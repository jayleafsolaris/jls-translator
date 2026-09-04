from ..common import state
from ..common.lang_io import parse_lang, write_lang, strip_comments_for_output
from ..common.state import PACKAGE_DIR, DEFAULTS
import sys
from ._convert_base_vars import _convert_base_vars


def load_base():
    base_path = state.SCRIPT_DIR / DEFAULTS["base_lang"]
    if not base_path.exists():
        sys.exit(f"Error: base file not found (expected '{DEFAULTS['base_lang']}' in {state.SCRIPT_DIR})")
    lines = parse_lang(base_path)
    # Process the lines to convert `{n}` to `%n$s` in memory
    return _convert_base_vars(lines)
