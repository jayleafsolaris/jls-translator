from ..common import state
from ..common.code_obfuscate import compile_code_text, decompile_code_text, is_compiled_code
from ..common.config_store import get_release_branch
from ..common.github_api import GitHubAuthError, GitHubApiError, is_sync_excluded, find_remote_package_prefix, get_branch_commit_and_tree, get_full_tree, get_blob_content, git_blob_sha
from ..common.progress import _report_keys
from ..common.state import GITHUB_REPO
from ._extract_code_compile_key import _extract_code_compile_key


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

    if "cli.py" not in remote_files:
        print(f"Failed to pull: no cli.py found under '{remote_prefix or '(repo root)'}' on branch "
              f"'{branch}' -- unexpected repo layout.")
        return

    written = 0
    undecoded = []
    total_files = len(remote_files)
    try:
        # cli.py is never compiled (see cmd_push.py) and carries this
        # pull's key in the clear -- fetch it first, always fresh
        # (skipping the usual "already up to date" check just for this
        # one file), so the key used to decompile everything else THIS
        # run is the one that actually matches what was just fetched,
        # even right after a key rotation.
        _report_keys("Pulling", 1, total_files)
        cli_content = get_blob_content(remote_files["cli.py"])
        code_key = _extract_code_compile_key(cli_content.decode("utf-8", errors="replace"))
        cli_dest = local_root / "cli.py"
        cli_dest.parent.mkdir(parents=True, exist_ok=True)
        cli_dest.write_bytes(cli_content)
        written += 1

        for done, (rel, sha) in enumerate(
            ((r, s) for r, s in remote_files.items() if r != "cli.py"), start=2
        ):
            _report_keys("Pulling", done, total_files)
            dest = local_root / rel

            if dest.exists():
                if rel.endswith(".py") and code_key is not None:
                    # Local .py files are kept decompiled/readable, but the
                    # remote blob is compiled -- comparing raw bytes would
                    # always mismatch and re-download every .py file on
                    # every single pull. Recompile the local content the
                    # same deterministic way --push does so this is an
                    # apples-to-apples comparison instead.
                    try:
                        local_compiled = compile_code_text(
                            dest.read_text(encoding="utf-8"), code_key
                        ).encode("utf-8")
                        if git_blob_sha(local_compiled) == sha:
                            continue
                    except UnicodeDecodeError:
                        pass  # fall through and just re-fetch it
                elif git_blob_sha(dest.read_bytes()) == sha:
                    continue  # already up to date -- skip the download

            content = get_blob_content(sha)
            if rel.endswith(".py"):
                text = content.decode("utf-8", errors="replace")
                if is_compiled_code(text):
                    if code_key is None:
                        undecoded.append(rel)
                    else:
                        try:
                            content = decompile_code_text(text, code_key).encode("utf-8")
                        except ValueError:
                            undecoded.append(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            written += 1
    except GitHubAuthError:
        print("\n\nFailed to pull: You are not authorized to do this")
        return
    except GitHubApiError as e:
        print(f"\n\nFailed to pull: {e}")
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
    print(f"\n\nPulled from '{branch}': {written} file(s) updated{note}.")
    if undecoded:
        print(f"Left compiled as-is (couldn't decompile -- corrupted, or cli.py itself was "
              f"corrupted): {', '.join(sorted(undecoded))}")
