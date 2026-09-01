"""--split: turn base into a base/ folder hierarchy mirroring every heading depth."""
from ..common import state
from ..common.state import DEFAULTS
from ..common.sections import (
    parse_tree, find_duplicate_siblings, write_tree, save_section_data,
)
from ..functions.cmd_split import cmd_split
