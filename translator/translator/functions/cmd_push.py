from ..common import state
from ..common.code_obfuscate import compile_code_text
from ..common.config_store import get_release_branch
from ..common.github_api import GitHubAuthError, GitHubApiError, is_sync_excluded, find_remote_package_prefix, get_branch_commit_and_tree, get_full_tree, create_blob, create_tree, create_commit, update_ref, git_blob_sha
from ..common.obfuscate import _KEY_LEN
from ..common.progress import _report_keys
from ..common.state import GITHUB_REPO
from ._local_files import _local_files
from ._set_hidden_code_key import _set_hidden_code_key
import secrets


def cmd_push(clean=False):
    local_root = state.SCRIPT_DIR / GITHUB_REPO
    if not local_root.is_dir():
        print(f"No '{GITHUB_REPO}/' folder found in this directory -- nothing to push. "
              f"Run --pull first to create it.")
        return

    cli_path = local_root / "cli.py"
    if not cli_path.is_file():
        print(f"No cli.py found directly under '{GITHUB_REPO}/' -- nothing to push. "
              f"Run --pull first to create a proper local checkout.")
        return

    if clean:
        # --clean skips all of this: no key rotation, no compiling, cli.py
        # left exactly as it is on disk. Primarily for testing, where
        # having to decompile every file back afterward just to read it
        # gets old fast.
        code_key = None
        cli_source = cli_path.read_text(encoding="utf-8")
    else:
        # A brand new random key every single push -- see cli.py's own
        # comment for why it lives hidden inside cli.py rather than a local
        # cache, and why it deliberately never stays stable. Every other
        # .py file gets (re)compiled with this new key below, and cli.py's
        # own hidden line is rewritten to match before it's uploaded too, so
        # this push is internally self-consistent even though the key just
        # changed.
        code_key = secrets.token_bytes(_KEY_LEN)
        cli_source = _set_hidden_code_key(cli_path.read_text(encoding="utf-8"), code_key)
        cli_path.write_text(cli_source, encoding="utf-8")

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
    # cli.py is the one .py file that never gets compiled -- it's the
    # anchor file that carries the (hidden) key in the clear (see cli.py's
    # own comment, and common/code_obfuscate.py's module docstring) so
    # any machine that ever gets a copy of it can decompile everything
    # else. Outside --clean, its key was just rotated above, and every
    # other .py file below gets recompiled with that new key regardless
    # of whether its own content changed, since the key changing means
    # the correct ciphertext changes too.
    cli_remote_path = f"{remote_prefix}/cli.py" if remote_prefix else "cli.py"

    if clean:
        print("--clean: pushing plain, uncompiled source (no key rotation).\n")

    entries = []
    total_files = len(local_files)
    try:
        for done, (path, local_path) in enumerate(local_files.items(), start=1):
            _report_keys("Pushing", done, total_files)
            if path == cli_remote_path:
                content = cli_source.encode("utf-8")
            else:
                content = local_path.read_bytes()
                if path.endswith(".py") and not clean:
                    content = compile_code_text(content.decode("utf-8"), code_key).encode("utf-8")
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
    except UnicodeDecodeError:
        print("\n\nFailed to push: a .py file under the repo folder isn't valid UTF-8 text -- "
              "fix its encoding and try again.")
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
