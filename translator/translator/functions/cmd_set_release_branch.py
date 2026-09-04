from ..common import config_store
from ..common.config_store import save_config_value, get_release_branch
from ..common.state import GITHUB_BRANCH


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
