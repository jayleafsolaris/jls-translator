import base64
from ..common.github_api import _API_ROOT
from ._request import _request


def get_blob_content(sha):
    """Returns the raw bytes of a blob."""
    data = _request("GET", f"{_API_ROOT}/git/blobs/{sha}")
    return base64.b64decode(data["content"])
