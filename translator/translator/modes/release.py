"""
--release: view or set which GitHub branch --upgrade downloads from, and
which branch the passive/manual update checker (--check) compares your
installed version against.

Persisted the same way --config --delay persists the request delay: saved
under the local config folder via config_store.save_config_value(), so it
survives across runs until changed again (or the config folder is reset
via --config --delete).
"""
from ..common import config_store
from ..common.state import GITHUB_BRANCH
from ..common.config_store import save_config_value, get_release_branch
from ..functions.cmd_set_release_branch import cmd_set_release_branch
from ..functions.cmd_show_release_branch import cmd_show_release_branch
