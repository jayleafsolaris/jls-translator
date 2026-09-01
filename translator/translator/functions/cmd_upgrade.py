from ..common.config_store import warn_red, get_release_branch
from ..common.netcheck import require_internet_or_warn, fetch_remote_version, _parse_version_tuple
from ..common.state import DEFAULTS, PACKAGE_DIR, GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME, SCRIPT_VERSION
import io
import os
import requests
import shutil
import sys
import zipfile
from ..modes.upgrade import _REQUIRED_TOP_LEVEL_FILES
from ._backup_and_clear import _backup_and_clear
from ._compare_versions import _compare_versions
from ._copy_skip_protected import _copy_skip_protected
from ._find_package_source import _find_package_source
from ._missing_required_files import _missing_required_files
from ._remove_non_protected import _remove_non_protected
from ._restore_backup import _restore_backup
from ._upgrade_protected_names import _upgrade_protected_names


def cmd_upgrade(enforce=False):
    """
    Fetches the latest zip from GitHub and replaces current files, then
    restarts. Downloads from whichever branch is currently configured as
    the release branch (see config_store.get_release_branch() -- defaults
    to GITHUB_BRANCH, overridable via --release <branch>), so pointing
    --release at e.g. a "dev" or "beta" branch makes --upgrade track that
    branch instead of the repo's normal default.

    Before downloading anything, compares the running version against the
    version on that branch's pyproject.toml:
      - identical and not --enforce: cancels, nothing is touched
      - remote older than local: proceeds, but labeled as a Downgrade
      - remote newer than local, or --enforce: proceeds as a normal Update
      - can't determine the remote version at all: aborts unless --enforce
    """
    branch = get_release_branch()
    branch_note = f" (branch: {branch})" if branch != GITHUB_BRANCH else ""

    print(f"Checking version{branch_note}...")
    if not require_internet_or_warn("--upgrade"):
        return

    remote_version = fetch_remote_version(timeout=3.0)
    if remote_version is None:
        if not enforce:
            warn_red("Couldn't determine the version on GitHub -- aborting. "
                      "Use --enforce to install anyway.")
            return
        comparison = None
    else:
        comparison = _compare_versions(remote_version)

    if comparison == 0 and not enforce:
        print("Already running the latest version:")
        print(f">> Version: v{SCRIPT_VERSION}")
        print(f">> Release: {branch}")
        return

    if comparison == -1:
        action, action_done = "Downgrading", "Downgrade"
    else:
        action, action_done = "Updating", "Update"

    UPDATE_URL = (
        f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{branch}.zip"
    )

    try:
        response = requests.get(UPDATE_URL, stream=True)
        if response.status_code == 404:
            warn_red(f"Invalid branch: '{branch}'")
            return
        response.raise_for_status()

        # PACKAGE_DIR (from common.state) is NOT the package root -- it's the
        # common/ folder itself (that's where state.py lives, and where it
        # computes cache/progress/config file paths relative to itself). The
        # actual package root -- the folder holding cli.py, common/, modes/,
        # and __init__.py -- is PACKAGE_DIR's parent. Every place this used to
        # copy/backup/verify directly against PACKAGE_DIR was therefore landing
        # one level too deep, e.g. producing common/common, common/modes, etc.
        package_root = os.path.dirname(str(PACKAGE_DIR))

        temp_dir = os.path.join(package_root, "temp_update")
        os.makedirs(temp_dir, exist_ok=True)

        print("Downloading...")
        protected = _upgrade_protected_names()
        skipped = []
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(temp_dir)
            print(f"{action}...")

            # GitHub zips put everything in a wrapper folder like
            # 'jls-translator-main'. The actual package (cli.py, common/,
            # modes/) lives one level deeper inside that -- find it rather
            # than assuming the wrapper folder is it.
            zip_root = os.path.join(temp_dir, z.namelist()[0])
            extracted_root = _find_package_source(zip_root)

            # Back up the current package contents instead of deleting them
            # outright, so a bad/incomplete copy can be rolled back. Any
            # protected persistent file (cache, progress, config) is left
            # in place wherever it actually lives in the tree -- not moved,
            # not touched -- regardless of depth.
            backup_dir = os.path.join(temp_dir, "_old_install_backup")
            os.makedirs(backup_dir, exist_ok=True)
            _backup_and_clear(package_root, backup_dir, protected)

            # Copy the fresh package in, again skipping protected names at
            # any depth so nothing the repo happens to ship under the same
            # name can clobber real persisted data.
            _copy_skip_protected(extracted_root, package_root, protected, skipped)

            # Verify the new install actually looks complete before we
            # commit to it. If _find_package_source picked the wrong
            # folder, or the zip was incomplete, restore the backup and
            # abort instead of restarting into a broken install.
            missing_files = _missing_required_files(package_root)
            if missing_files:
                _remove_non_protected(package_root, protected)
                _restore_backup(backup_dir, package_root)
                shutil.rmtree(temp_dir)
                warn_red(
                    f"{action} looked incomplete (missing: " + ", ".join(missing_files) + "). "
                    "Restored your previous install untouched -- nothing was changed."
                )
                return

            # LICENSE / pyproject.toml live at the repo root (zip_root),
            # which is two levels above package_root (package_root's
            # parent is the outer wrapper folder, whose parent is the
            # repo root) -- matching the same relative position in the
            # install.
            install_root = os.path.dirname(os.path.dirname(package_root))
            missing_required = []
            for fname in _REQUIRED_TOP_LEVEL_FILES:
                top_src = os.path.join(zip_root, fname)
                if os.path.isfile(top_src):
                    shutil.copy2(top_src, os.path.join(install_root, fname))
                else:
                    missing_required.append(fname)

        shutil.rmtree(temp_dir)
        print(f"{action_done} complete!{branch_note}")
        if skipped:
            print(f"Left your local cache/config untouched (repo also had: {', '.join(sorted(skipped))}).")
        if missing_required:
            warn_red(f"Could not find in repo, so left untouched: {', '.join(sorted(missing_required))}")

        # Strip --upgrade (and --enforce) from args so it doesn't loop
        # infinitely upon restart
        new_args = [arg for arg in sys.argv if arg not in ("--upgrade", "--enforce")]
        if len(new_args) == 1:
            new_args.append("--version") # Just show the version if they ran it raw

        os.execv(sys.executable, [sys.executable] + new_args)

    except Exception as e:
        warn_red(f"{action_done} failed: {e}")
