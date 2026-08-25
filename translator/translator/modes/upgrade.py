"""--upgrade: fetch the latest release from GitHub and replace this install."""

import io
import os
import shutil
import sys
import zipfile

import requests

from ..common.state import DEFAULTS, PACKAGE_DIR, GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME
from ..common.config_store import warn_red
from ..common.netcheck import require_internet_or_warn

def _upgrade_protected_names():
    """
    Basenames (files or folders) inside the package that --upgrade must
    never overwrite, delete, or merge into, no matter what happens to be
    sitting in the downloaded repo zip under the same name, and no matter
    how deep in the tree they actually live (e.g. common/cache.json).

    This exists because the cache, progress file, languages.json, the
    version-check cache, and the config folder all deliberately live
    somewhere inside the installed package -- the same tree --upgrade
    replaces with a fresh GitHub download. Any matching filename in the
    repo would otherwise silently overwrite the user's real cache/config
    with whatever happens to be committed (or not committed at all, which
    is just as bad), which is exactly the "my config got wiped by
    --upgrade" bug this guards against.
    """
    return {
        DEFAULTS["cache_file"],
        DEFAULTS["languages_json"],
        DEFAULTS["progress_file"],
        DEFAULTS["update_temp_file"],
        DEFAULTS["version_check_file"],
        CONFIG_DIR_HIDDEN_NAME,
        CONFIG_DIR_VISIBLE_NAME,
        "temp_update",  # --upgrade's own scratch dir, in case it ever lingers
    }


def _find_package_source(extracted_root):
    """
    GitHub wraps the whole repo in a single top-level folder (e.g.
    'translator-main/'). In this repo that wrapper folder is NOT the package
    itself -- the real package (cli.py, common/, modes/) lives one level
    deeper, at 'translator-main/translator/'. Walk the extracted tree and
    return the directory that actually contains cli.py, rather than assuming
    the zip's outer wrapper folder is it. Falls back to extracted_root if no
    such directory is found, so an unexpected layout doesn't hard-crash.
    """
    for dirpath, dirnames, filenames in os.walk(extracted_root):
        if "cli.py" in filenames:
            return dirpath
    return extracted_root


def _contains_protected(dir_path, protected):
    """True if dir_path contains a protected-named file/folder anywhere below it."""
    for dirpath, dirnames, filenames in os.walk(dir_path):
        for name in dirnames + filenames:
            if name in protected:
                return True
    return False


def _backup_and_clear(src_dir, backup_dir, protected):
    """
    Recursively move everything under src_dir into backup_dir, EXCEPT any
    file or directory whose basename is in `protected` -- those are left
    exactly where they are, at whatever depth they live, so persistent
    state (cache, progress, config) survives regardless of which folder
    it happens to live in (e.g. common/cache.json). A directory that
    itself isn't a protected name but contains a protected descendant is
    recursed into rather than moved wholesale, so the protected file
    inside it stays put while everything around it still gets replaced.
    """
    for entry in os.listdir(src_dir):
        if entry in protected:
            continue
        s = os.path.join(src_dir, entry)
        d = os.path.join(backup_dir, entry)
        if os.path.isdir(s) and _contains_protected(s, protected):
            os.makedirs(d, exist_ok=True)
            _backup_and_clear(s, d, protected)
            if not os.listdir(s):
                os.rmdir(s)
        else:
            shutil.move(s, d)


def _copy_skip_protected(src_dir, dst_dir, protected, skipped):
    """
    Recursively copy src_dir's contents into dst_dir, skipping (not
    overwriting) any file or directory whose basename is in `protected`,
    at any depth -- mirrors _backup_and_clear so persistent files that
    survived the backup step are never clobbered by the fresh copy.
    """
    os.makedirs(dst_dir, exist_ok=True)
    for entry in os.listdir(src_dir):
        if entry in protected:
            skipped.append(entry)
            continue
        s = os.path.join(src_dir, entry)
        d = os.path.join(dst_dir, entry)
        if os.path.isdir(s):
            _copy_skip_protected(s, d, protected, skipped)
        else:
            shutil.copy2(s, d)


def _remove_non_protected(dir_path, protected):
    """Recursively delete everything under dir_path except protected-named items."""
    for entry in os.listdir(dir_path):
        if entry in protected:
            continue
        target = os.path.join(dir_path, entry)
        if os.path.isdir(target) and _contains_protected(target, protected):
            _remove_non_protected(target, protected)
            if not os.listdir(target):
                os.rmdir(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)


def _restore_backup(backup_dir, dst_dir):
    """Recursively move everything from backup_dir back into dst_dir."""
    for entry in os.listdir(backup_dir):
        s = os.path.join(backup_dir, entry)
        d = os.path.join(dst_dir, entry)
        if os.path.isdir(s) and os.path.isdir(d):
            _restore_backup(s, d)
            if not os.listdir(s):
                os.rmdir(s)
        else:
            shutil.move(s, d)


# Repo-root files (siblings of the outer package folder, not inside it)
# that still need to make it into the install -- handled separately from
# the package copy loop since they live one level further out.
_REQUIRED_TOP_LEVEL_FILES = {"LICENSE", "pyproject.toml"}

# Files that MUST exist in a working install, checked (as relative paths
# from the package root) after copying the new version in. If any are
# missing, the copy was incomplete -- e.g. _find_package_source picked the
# wrong folder, or the download was truncated -- and we roll back rather
# than restart into a broken install with no clear error.
_REQUIRED_PACKAGE_FILES = [
    "cli.py",
    os.path.join("common", "state.py"),
    os.path.join("common", "config_store.py"),
    os.path.join("common", "netcheck.py"),
    os.path.join("modes", "upgrade.py"),
]


def _missing_required_files(package_root):
    return [f for f in _REQUIRED_PACKAGE_FILES if not os.path.isfile(os.path.join(package_root, f))]


def cmd_upgrade():
    """Fetches the latest main.zip from GitHub, replaces current files, and restarts."""
    UPDATE_URL = (
        f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
    )

    print("Checking for updates...")
    if not require_internet_or_warn("--upgrade"):
        return

    # PACKAGE_DIR (from common.state) is NOT the package root -- it's the
    # common/ folder itself (that's where state.py lives, and where it
    # computes cache/progress/config file paths relative to itself). The
    # actual package root -- the folder holding cli.py, common/, modes/,
    # and __init__.py -- is PACKAGE_DIR's parent. Every place this used to
    # copy/backup/verify directly against PACKAGE_DIR was therefore landing
    # one level too deep, e.g. producing common/common, common/modes, etc.
    package_root = os.path.dirname(str(PACKAGE_DIR))

    try:
        response = requests.get(UPDATE_URL, stream=True)
        response.raise_for_status()

        temp_dir = os.path.join(package_root, "temp_update")
        os.makedirs(temp_dir, exist_ok=True)

        print("Downloading...")
        protected = _upgrade_protected_names()
        skipped = []
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(temp_dir)
            print("Updating...")

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
                    "Update looked incomplete (missing: " + ", ".join(missing_files) + "). "
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
        print(f"Update complete!")
        if skipped:
            print(f"Left your local cache/config untouched (repo also had: {', '.join(sorted(skipped))}).")
        if missing_required:
            warn_red(f"Could not find in repo, so left untouched: {', '.join(sorted(missing_required))}")

        # Strip --upgrade from args so it doesn't loop infinitely upon restart
        new_args = [arg for arg in sys.argv if arg != "--upgrade"]
        if len(new_args) == 1:
            new_args.append("--version") # Just show the version if they ran it raw

        os.execv(sys.executable, [sys.executable] + new_args)

    except Exception as e:
        warn_red(f"Update failed: {e}")
