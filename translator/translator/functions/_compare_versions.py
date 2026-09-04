from ..common.netcheck import require_internet_or_warn, fetch_remote_version, _parse_version_tuple
from ..common.state import DEFAULTS, PACKAGE_DIR, GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME, SCRIPT_VERSION
from ._pad import _pad


def _compare_versions(remote_version, local_version=SCRIPT_VERSION):
    """
    Returns -1, 0, or 1 (remote older / identical / newer than local),
    padding both parsed tuples to the same length first so e.g. '1.2' and
    '1.2.0' compare as identical rather than one looking like a downgrade
    of the other just because it has fewer segments.
    """
    remote_t = _parse_version_tuple(remote_version)
    local_t = _parse_version_tuple(local_version)
    n = max(len(remote_t), len(local_t))
    remote_t, local_t = _pad(remote_t, n), _pad(local_t, n)
    if remote_t == local_t:
        return 0
    return -1 if remote_t < local_t else 1
