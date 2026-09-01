from ..common.github_api import _API_ROOT
from ._request import _request


def get_branch_commit_and_tree(branch):
    """Returns (commit_sha, tree_sha) for the given branch's current HEAD."""
    ref = _request("GET", f"{_API_ROOT}/git/refs/heads/{branch}")
    commit_sha = ref["object"]["sha"]
    commit = _request("GET", f"{_API_ROOT}/git/commits/{commit_sha}")
    return commit_sha, commit["tree"]["sha"]
