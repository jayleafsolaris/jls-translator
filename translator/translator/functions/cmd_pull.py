from ..common import state
from ..common.config_store import get_release_branch
from ..common.github_api import GitHubAuthError, GitHubApiError, is_sync_excluded, find_remote_package_prefix, get_branch_commit_and_tree, get_full_tree, get_blob_content, git_blob_sha
from ..common.state import GITHUB_REPO


def cmd_pull():
    branch = get_release_branch()
    local_root = state.SCRIPT_DIR / GITHUB_REPO

    try:
        _, tree_sha = get_branch_commit_and_tree(branch)
        remote_tree = get_full_tree(tree_sha)
    except GitHubAuthError:
        print("Failed to pull: You are not authorized to do this")
        return
    except GitHubApiError as e:
        print(f"Failed to pull: {e}")
        return

    remote_prefix = find_remote_package_prefix(remote_tree)
    if remote_prefix is None:
        print(f"Failed to pull: couldn't find cli.py anywhere in the repo's tree "
              f"on branch '{branch}' -- unexpected repo layout.")
        return

    remote_files = {}
    for e in remote_tree:
        if e["type"] != "blob":
            continue
        if not (e["path"] == remote_prefix or e["path"].startswith(f"{remote_prefix}/")):
            continue
        rel = e["path"][len(remote_prefix) + 1:] if remote_prefix else e["path"]
        if is_sync_excluded(rel):
            continue
        remote_files[rel] = e["sha"]

    if not remote_files:
        print(f"Nothing found under '{remote_prefix or '(repo root)'}' on branch '{branch}' -- nothing to pull.")
        return

    written = 0
    try:
        for rel, sha in remote_files.items():
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

    # Mirror deletions: remove local files no longer present remotely --
    # but never a protected (cache/config/token) file, even if it doesn't
    # exist in the repo, which it never will.
    removed = 0
    for p in local_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(local_root).as_posix()
            if is_sync_excluded(rel):
                continue
            if rel not in remote_files:
                p.unlink()
                removed += 1

    note = f", removed {removed} stale local file(s)" if removed else ""
    print(f"Pulled from '{branch}': {written} file(s) updated{note}.")
