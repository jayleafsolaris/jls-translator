"""--pull: sync <cwd>/jls-translator/ down from this tool's own repo, mirroring it exactly."""

from ..common import state
from ..common.config_store import get_release_branch
from ..common.github_api import (
    GitHubAuthError, GitHubApiError, SYNC_PREFIX,
    get_branch_commit_and_tree, get_full_tree, get_blob_content, git_blob_sha,
)


def cmd_pull():
    branch = get_release_branch()
    local_root = state.SCRIPT_DIR / SYNC_PREFIX

    try:
        _, tree_sha = get_branch_commit_and_tree(branch)
        remote_tree = get_full_tree(tree_sha)
    except GitHubAuthError:
        print("Failed to pull: You are not authorized to do this")
        return
    except GitHubApiError as e:
        print(f"Failed to pull: {e}")
        return

    remote_files = {
        e["path"]: e["sha"] for e in remote_tree
        if e["type"] == "blob" and e["path"].startswith(f"{SYNC_PREFIX}/")
    }

    if not remote_files:
        print(f"No '{SYNC_PREFIX}/' path found on branch '{branch}' -- nothing to pull.")
        return

    local_root.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        for path, sha in remote_files.items():
            rel = path[len(SYNC_PREFIX) + 1:]
            dest = local_root / rel
            if dest.exists() and git_blob_sha(dest.read_bytes()) == sha:
                continue  # already up to date -- skip the download
            content = get_blob_content(sha)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            written += 1
    except GitHubAuthError:
        print("Failed to pull: You are not authorized to do this")
        return
    except GitHubApiError as e:
        print(f"Failed to pull: {e}")
        return

    # Mirror deletions: remove local files no longer present remotely
    remote_rels = {p[len(SYNC_PREFIX) + 1:] for p in remote_files}
    removed = 0
    for p in local_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(local_root).as_posix()
            if rel not in remote_rels:
                p.unlink()
                removed += 1

    note = f", removed {removed} stale local file(s)" if removed else ""
    print(f"Pulled from '{branch}': {written} file(s) updated{note}.")