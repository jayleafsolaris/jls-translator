from ..common.config_store import save_config_value, get_release_branch
from ..common.state import GITHUB_BRANCH


def cmd_show_release_branch():
    """`--release` with no branch given: show the currently configured branch."""
    current = get_release_branch()
    note = " (default)" if current == GITHUB_BRANCH else ""
    print(f"Current release branch: {current}{note}")
    print()
    print("This is the branch --upgrade downloads from, and the branch the")
    print("update checker (--check, and the passive check on every command)")
    print("compares your installed version against.")
    print()
    print("Run --release <branch> to change it.")
