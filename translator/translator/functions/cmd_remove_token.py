from ..common.github_api import get_token, set_token, remove_token


def cmd_remove_token():
    if remove_token():
        print("GitHub token removed.")
    else:
        print("No GitHub token was set.")
