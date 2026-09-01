from ..common.github_api import get_token, set_token, remove_token
from ._mask import _mask


def cmd_show_token():
    token = get_token()
    if token:
        print(f"GitHub token is set: {_mask(token)}")
    else:
        print("No GitHub token is set. Use --token <TOKEN> to add one.")
