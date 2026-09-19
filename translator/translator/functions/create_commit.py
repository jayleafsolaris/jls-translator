from ..common.github_api import _API_ROOT
from ._request import _request


def create_commit(message, tree_sha, parent_sha):
    data = _request("POST", f"{_API_ROOT}/git/commits", json={
        "message": message,
        "tree": tree_sha,
        "parents": [parent_sha],
    })
    return data["sha"]
