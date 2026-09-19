"""--view: list base + .lang files in this folder, with sizes and key counts."""
from ..common import state
from ..common.state import DEFAULTS
from ..common.lang_io import parse_lang, entries_dict
from ..common.progress import _human_size
from ..common.cache import get_update_count
from ..functions.cmd_view import cmd_view
