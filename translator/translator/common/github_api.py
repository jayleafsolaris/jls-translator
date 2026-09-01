"""
GitHub API helpers for --push/--pull (Git Data API: blobs, trees, commits,
refs) and --token (storing/removing the personal access token those calls
authenticate with).

--push/--pull always sync one local folder -- <cwd>/jls-translator/ --
against the exact same-named path in this tool's OWN repo
(GITHUB_OWNER/GITHUB_REPO, from state.py -- not some separately configured
project repo), on whichever branch config_store.get_release_branch()
currently points to (the same branch --upgrade/--release use).
"""
import base64
import hashlib
import os
import requests
from .state import (
    GITHUB_OWNER, GITHUB_REPO, PACKAGE_DIR, DEFAULTS,
    CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME,
)
from .config_store import load_config_value, save_config_value, current_config_dir
_TOKEN_CONFIG_NAME = "github_token"
_API_ROOT = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
_PROTECTED_NAMES = {
    DEFAULTS["cache_file"], DEFAULTS["languages_json"], DEFAULTS["progress_file"],
    DEFAULTS["update_temp_file"], DEFAULTS["version_check_file"], DEFAULTS["section_order_cache"],
    DEFAULTS["base_backup_file"],
    CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME, "temp_update", "__pycache__", ".git",
}
class GitHubAuthError(Exception):
    """Raised whenever the API responds 401/403/404 -- treated uniformly as 'not authorized'."""
    pass
class GitHubApiError(Exception):
    """Any other API failure (network, 5xx, unexpected response shape, truncated tree, etc)."""
    pass
from ..functions._headers import _headers
from ..functions._request import _request
from ..functions.create_blob import create_blob
from ..functions.create_commit import create_commit
from ..functions.create_tree import create_tree
from ..functions.find_remote_package_prefix import find_remote_package_prefix
from ..functions.get_blob_content import get_blob_content
from ..functions.get_branch_commit_and_tree import get_branch_commit_and_tree
from ..functions.get_full_tree import get_full_tree
from ..functions.get_token import get_token
from ..functions.git_blob_sha import git_blob_sha
from ..functions.is_sync_excluded import is_sync_excluded
from ..functions.remove_token import remove_token
from ..functions.set_token import set_token
from ..functions.update_ref import update_ref
