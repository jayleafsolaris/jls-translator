from ..common.github_api import _PROTECTED_NAMES


def is_sync_excluded(rel_posix_path):
    """True if this path (relative to the install root) must be skipped by
    both --push and --pull -- persistent local state, never repo content."""
    if rel_posix_path.endswith(".pyc"):
        return True
    return any(part in _PROTECTED_NAMES for part in rel_posix_path.split("/"))
