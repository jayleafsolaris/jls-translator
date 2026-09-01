from ..common import state
from ..common.config_store import get_release_branch
from ..common.github_api import GitHubAuthError, GitHubApiError, is_sync_excluded, find_remote_package_prefix, get_branch_commit_and_tree, get_full_tree, create_blob, create_tree, create_commit, update_ref, git_blob_sha
from ..common.progress import _report_keys
from ..common.state import GITHUB_REPO
from ._local_files import _local_files


def cmd_push():
    local_root = state.SCRIPT_DIR / GITHUB_REPO
    if not local_root.is_dir():
        print(f"No '{GITHUB_REPO}/' folder found in this directory -- nothing to push. "
              f"Run --pull first to create it.")
        return

    branch = get_release_branch()

    try:
        commit_sha, tree_sha = get_branch_commit_and_tree(branch)
        remote_tree = get_full_tree(tree_sha)
    except GitHubAuthError:
        print("Failed to push: You are not authorized to do this")
        return
    except GitHubApiError as e:
        print(f"Failed to push: {e}")
        return

    remote_prefix = find_remote_package_prefix(remote_tree)
    if remote_prefix is None:
        print("Failed to push: couldn't find cli.py anywhere in the repo's tree "
              f"on branch '{branch}' -- unexpected repo layout.")
        return

    remote_files = {
        e["path"]: e["sha"] for e in remote_tree
        if e["type"] == "blob"
        and (e["path"] == remote_prefix or e["path"].startswith(f"{remote_prefix}/"))
        and not is_sync_excluded(e["path"][len(remote_prefix) + 1:] if remote_prefix else e["path"])
    }
    local_files = _local_files(local_root, remote_prefix)

    entries = []
    total_files = len(local_files)
    try:
        for done, (path, local_path) in enumerate(local_files.items(), start=1):
            _report_keys("Pushing", done, total_files)
            content = local_path.read_bytes()
            if remote_files.get(path) == git_blob_sha(content):
                continue  # unchanged -- don't even upload a blob for it
            blob_sha = create_blob(content)
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})

        for path in remote_files:
            if path not in local_files:
                entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
    except GitHubAuthError:
        print("\n\nFailed to push: You are not authorized to do this")
        return
    except GitHubApiError as e:
        print(f"\n\nFailed to push: {e}")
        return

    if not entries:
        print(f"\n\nNothing to push -- already matches '{branch}'.")
        return

    changed = sum(1 for e in entries if e["sha"] is not None)
    removed = sum(1 for e in entries if e["sha"] is None)

    try:
        new_tree_sha = create_tree(tree_sha, entries)
        new_commit_sha = create_commit(
            f"Syncronized", new_tree_sha, commit_sha
        )
        update_ref(branch, new_commit_sha)
    except GitHubAuthError:
        print("\n\nFailed to push: You are not authorized to do this")
        return
    except GitHubApiError as e:
        print(f"\n\nFailed to push: {e}")
        return

    print(f"\n\nPushed to '{branch}': {changed} file(s) updated, {removed} file(s) removed.")
