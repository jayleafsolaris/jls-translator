from ..common.github_api import get_token, set_token, remove_token
from ._mask import _mask


def cmd_set_token(token):
    set_token(token)
    print(f"GitHub token saved: {_mask(token)}")
