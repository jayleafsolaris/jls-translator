"""
Internet connectivity probing and the passive/manual GitHub version-check
used for the update notice, --check, and --upgrade.
"""
import concurrent.futures
import json
import re
import time
import requests
from .state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION
from .config_store import warn_red, _RESET, get_release_branch
from .progress import format_duration
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
from ..functions._branch_suffix import _branch_suffix
from ..functions._load_version_check_cache import _load_version_check_cache
from ..functions._parse_version_tuple import _parse_version_tuple
from ..functions._save_version_check_cache import _save_version_check_cache
from ..functions.check_for_update_notice import check_for_update_notice
from ..functions.check_internet import check_internet
from ..functions.cmd_check_update import cmd_check_update
from ..functions.cmd_set_autocheck import cmd_set_autocheck
from ..functions.fetch_remote_version import fetch_remote_version
from ..functions.require_internet_or_warn import require_internet_or_warn
