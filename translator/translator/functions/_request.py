import requests
from ..common.github_api import GitHubApiError, GitHubAuthError
from ._headers import _headers


def _request(method, url, **kwargs):
    try:
        resp = requests.request(method, url, headers=_headers(), timeout=15, **kwargs)
    except requests.RequestException as e:
        raise GitHubApiError(str(e))

    # 404 is included here because GitHub returns 404 (not 403) for a
    # private repo you can't see, to avoid confirming it exists -- from
    # the caller's perspective that's still "not authorized".
    if resp.status_code in (401, 403, 404):
        raise GitHubAuthError()
    if not resp.ok:
        raise GitHubApiError(f"GitHub API returned {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}
