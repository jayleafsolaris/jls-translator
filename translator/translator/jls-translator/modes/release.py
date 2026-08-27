"""
--release: view or set which GitHub branch --upgrade downloads from, and
which branch the passive/manual update checker (--check) compares your
installed version against.

Persisted the same way --config --delay persists the request delay: saved
under the local config folder via config_store.save_config_value(), so it
survives across runs until changed again (or the config folder is reset
via --config --delete).
"""

from ..common import config_store
from ..common.state import GITHUB_BRANCH
from ..common.config_store import save_config_value, get_release_branch


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


def cmd_set_release_branch(branch):
    """`--release <branch>`: persist a new release branch."""
    branch = branch.strip()
    if not branch:
        print("No branch given -- nothing changed.")
        return

    save_config_value("release_branch", branch)
    # Bust config_store's cached value so the new branch takes effect
    # immediately within this same run too (e.g. if a script runs
    # --release <branch> immediately followed by --upgrade), not just on
    # the next invocation of the tool.
    config_store._CONFIG_RELEASE_BRANCH = branch

    note = " (this is the repo's normal default branch)" if branch == GITHUB_BRANCH else ""
    print(f"Saved: release branch = {branch}{note}")
    print("--upgrade and the update checker will now use this branch.")