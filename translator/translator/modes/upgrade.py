"""--upgrade: fetch the latest release from GitHub and replace this install."""
import io
import os
import shutil
import sys
import zipfile
import requests
from ..common.state import (
    DEFAULTS, PACKAGE_DIR, GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH,
    CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME, SCRIPT_VERSION,
)
from ..common.config_store import warn_red, get_release_branch
from ..common.netcheck import require_internet_or_warn, fetch_remote_version, _parse_version_tuple
_REQUIRED_TOP_LEVEL_FILES = {"LICENSE", "pyproject.toml"}
_REQUIRED_PACKAGE_FILES = [
    "cli.py",
    os.path.join("common", "state.py"),
    os.path.join("common", "config_store.py"),
    os.path.join("common", "netcheck.py"),
    os.path.join("modes", "upgrade.py"),
]
from ..functions._backup_and_clear import _backup_and_clear
from ..functions._compare_versions import _compare_versions
from ..functions._contains_protected import _contains_protected
from ..functions._copy_skip_protected import _copy_skip_protected
from ..functions._find_package_source import _find_package_source
from ..functions._missing_required_files import _missing_required_files
from ..functions._pad import _pad
from ..functions._remove_non_protected import _remove_non_protected
from ..functions._restore_backup import _restore_backup
from ..functions._upgrade_protected_names import _upgrade_protected_names
from ..functions.cmd_upgrade import cmd_upgrade
