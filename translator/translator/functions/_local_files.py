from ..common.github_api import GitHubAuthError, GitHubApiError, is_sync_excluded, find_remote_package_prefix, get_branch_commit_and_tree, get_full_tree, create_blob, create_tree, create_commit, update_ref, git_blob_sha


def _local_files(local_root, remote_prefix):
    """Returns {remote_path: absolute_path} for every non-excluded file under local_root."""
    files = {}
    for p in local_root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(local_root).as_posix()
        if is_sync_excluded(rel):
            continue
        remote_path = f"{remote_prefix}/{rel}" if remote_prefix else rel
        files[remote_path] = p
    return files
