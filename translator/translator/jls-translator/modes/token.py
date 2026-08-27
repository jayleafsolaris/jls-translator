"""--token: add or remove the GitHub personal access token used by --push/--pull."""

from ..common.github_api import get_token, set_token, remove_token


def _mask(token):
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}…{token[-4:]}"


def cmd_show_token():
    token = get_token()
    if token:
        print(f"GitHub token is set: {_mask(token)}")
    else:
        print("No GitHub token is set. Use --token <TOKEN> to add one.")


def cmd_set_token(token):
    set_token(token)
    print(f"GitHub token saved: {_mask(token)}")


def cmd_remove_token():
    if remove_token():
        print("GitHub token removed.")
    else:
        print("No GitHub token was set.")
