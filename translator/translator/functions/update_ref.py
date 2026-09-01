from ..common.github_api import _API_ROOT
from ._request import _request


def update_ref(branch, commit_sha):
    _request("PATCH", f"{_API_ROOT}/git/refs/heads/{branch}", json={"sha": commit_sha})
