from ..common.github_api import GitHubApiError, _API_ROOT
from ._request import _request


def get_full_tree(tree_sha):
    """Returns the full recursive tree: a list of {path, mode, type, sha, ...} dicts."""
    data = _request("GET", f"{_API_ROOT}/git/trees/{tree_sha}", params={"recursive": "1"})
    if data.get("truncated"):
        raise GitHubApiError("Repo tree is too large for a single recursive fetch (GitHub truncated it).")
    return data.get("tree", [])
