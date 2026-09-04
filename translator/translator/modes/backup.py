"""--backup: zip base (file or split base/ hierarchy) + all .lang files (+ cache/languages.json) into lang_backups/."""
import zipfile
from datetime import datetime
from ..common import state
from ..common.state import DEFAULTS, PACKAGE_DIR
from ..functions.cmd_backup import cmd_backup
