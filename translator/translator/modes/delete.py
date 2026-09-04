"""--delete: delete every generated .lang file (base is kept)."""
import sys
import time
from ..common import state
from ..common.state import DEFAULTS
from ..common.progress import load_progress, save_progress, clear_progress, format_duration, _ask_continue
from ..functions.cmd_delete import cmd_delete
