"""
--config and its subcommands: worker count, delay, active languages,
and hiding/showing/deleting the config folder.
"""
import os
import shutil
import sys
from ..common import state, config_store
from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME
from ..common.config_store import load_config_value, save_config_value, get_request_delay, config_dir_state
from ..common.cache import compute_auto_workers, get_active_language_codes, save_active_language_codes
from ..functions._curses_available import _curses_available
from ..functions._edit_active_languages_curses import _edit_active_languages_curses
from ..functions._edit_active_languages_text import _edit_active_languages_text
from ..functions._set_windows_hidden_attribute import _set_windows_hidden_attribute
from ..functions.cmd_config_delay import cmd_config_delay
from ..functions.cmd_config_delete import cmd_config_delete
from ..functions.cmd_config_hide import cmd_config_hide
from ..functions.cmd_config_languages import cmd_config_languages
from ..functions.cmd_config_menu import cmd_config_menu
from ..functions.cmd_config_show import cmd_config_show
from ..functions.cmd_config_workers import cmd_config_workers
