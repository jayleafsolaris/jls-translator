"""--compile: obfuscate base's raw text with a fresh random key each run."""
from ..common import state
from ..common.state import DEFAULTS
from ..common.obfuscate import compile_text, is_compiled
from ..common.cache import save_compile_key
from ..functions.cmd_compile import cmd_compile
