"""--cache and its subcommands: rebuild, view info about, or clear the translation cache."""
from ..common.state import DEFAULTS, PACKAGE_DIR
from ..common.progress import load_base, clear_progress, _human_size
from ..common.lang_io import entries_dict
from ..common.cache import save_cache, get_update_count, write_update_count, clear_cache, load_cache
from ..functions.cmd_cache_build import cmd_cache_build
from ..functions.cmd_cache_clear import cmd_cache_clear
from ..functions.cmd_cache_menu import cmd_cache_menu
from ..functions.cmd_cache_view import cmd_cache_view
