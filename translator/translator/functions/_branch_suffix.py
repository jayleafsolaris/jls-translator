from ..common.config_store import warn_red, _RESET, get_release_branch
from ..common.state import GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, PACKAGE_DIR, DEFAULTS, SCRIPT_VERSION


def _branch_suffix():
    """
    A short " (Current Branch: X)" annotation appended to update-notice
    messages whenever the release branch has been overridden away from
    the repo's normal default (GITHUB_BRANCH) -- so a custom branch's
    version checks are clearly labeled, while the common default-branch
    case stays exactly as quiet/plain as before.
    """
    branch = get_release_branch()
    if branch == GITHUB_BRANCH:
        return ""
    return f" (Current Branch: {branch})"
