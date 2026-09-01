"""--merge: rebuild base from the base/ folder hierarchy created by --split."""
import shutil
from ..common import state
from ..common.state import DEFAULTS
from ..common.sections import load_section_data, render_tree
from ..functions.cmd_merge import cmd_merge
