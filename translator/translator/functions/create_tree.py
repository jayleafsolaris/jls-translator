from ..common.github_api import _API_ROOT
from ._request import _request


def create_tree(base_tree_sha, entries):
    """entries: list of {"path", "mode", "type", "sha"} dicts. A "sha" of None
    deletes that path from the resulting tree (relative to base_tree)."""
    data = _request("POST", f"{_API_ROOT}/git/trees", json={
        "base_tree": base_tree_sha,
        "tree": entries,
    })
    return data["sha"]
