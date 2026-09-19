"""--restore: restore base + .lang files (+ split section folders + cache/languages.json) from a lang_backups/ zip."""
import shutil
import zipfile
from ..common import state
from ..common.state import DEFAULTS, PACKAGE_DIR
from ..common.progress import _human_size
_PACKAGE_SCOPED = {DEFAULTS["cache_file"], DEFAULTS["languages_json"], DEFAULTS["section_order_cache"]}
from ..functions.cmd_restore import cmd_restore
