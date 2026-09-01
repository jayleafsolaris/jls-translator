import base64
from ..common.github_api import _API_ROOT
from ._request import _request


def create_blob(content_bytes):
    data = _request("POST", f"{_API_ROOT}/git/blobs", json={
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "encoding": "base64",
    })
    return data["sha"]
