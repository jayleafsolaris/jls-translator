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
    Basenames (files or folders) inside PACKAGE_DIR that --upgrade must
    never overwrite, delete, or merge into, no matter what happens to be
    sitting in the downloaded repo zip under the same name.

    This exists because the cache, progress file, languages.json, the
    version-check cache, and the config folder all deliberately live right
    next to the installed package (see the PACKAGE_DIR comment above) --
    the same directory --upgrade copies the fresh GitHub download into. Any
    matching filename in the repo would otherwise silently overwrite the
    user's real cache/config with whatever happens to be committed (or not
    committed at all, which is just as bad), which is exactly the "my
    config got wiped by --upgrade" bug this guards against.
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


# Repo-root files (siblings of the package folder, not inside it) that
# still need to make it into the install -- these live next to PACKAGE_DIR,
# not inside it, so they're handled separately from the package copy loop.
_REQUIRED_TOP_LEVEL_FILES = {"LICENSE", "pyproject.toml"}

# Files that MUST exist in a working install, checked (as relative paths
# from PACKAGE_DIR) after copying the new version in. If any are missing,
# the copy was incomplete -- e.g. _find_package_source picked the wrong
# folder, or the download was truncated -- and we roll back rather than
# restart into a broken install with no clear error.
_REQUIRED_PACKAGE_FILES = [
    "cli.py",
    os.path.join("common", "state.py"),
    os.path.join("common", "config_store.py"),
    os.path.join("common", "netcheck.py"),
    os.path.join("modes", "upgrade.py"),
]


def _missing_required_files(package_dir):
    return [f for f in _REQUIRED_PACKAGE_FILES if not os.path.isfile(os.path.join(package_dir, f))]


def cmd_upgrade():
    """Fetches the latest main.zip from GitHub, replaces current files, and restarts."""
    UPDATE_URL = (
        f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
    )
    
    print("Checking for updates...")
    if not require_internet_or_warn("--upgrade"):
        return

    try:
        response = requests.get(UPDATE_URL, stream=True)
        response.raise_for_status()

        temp_dir = PACKAGE_DIR / "temp_update"
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
            # outright. copytree(dirs_exist_ok=True)/copy2 only overwrite
            # matching filenames and never remove files that were
            # deleted/renamed upstream, so a straight merge lets stale
            # files pile up forever -- but wiping first is risky if the
            # new copy turns out incomplete (wrong source folder, network
            # hiccup mid-zip, etc). Move everything non-protected into a
            # backup dir under temp_update instead, so we can restore it if
            # the new install fails verification below.
            backup_dir = os.path.join(temp_dir, "_old_install_backup")
            os.makedirs(backup_dir, exist_ok=True)
            for item in os.listdir(PACKAGE_DIR):
                if item in protected:
                    continue
                shutil.move(os.path.join(PACKAGE_DIR, item), os.path.join(backup_dir, item))

            # Move files from the extracted package folder directly into
            # the script's package dir -- except anything that would
            # clobber local cache/config/progress state.
            for item in os.listdir(extracted_root):
                if item in protected:
                    skipped.append(item)
                    continue

                src = os.path.join(extracted_root, item)
                dst = os.path.join(PACKAGE_DIR, item)
                
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

            # Verify the new install actually looks complete before we
            # commit to it. If _find_package_source picked the wrong
            # folder, or the zip was incomplete, restore the backup and
            # abort instead of restarting into a broken install.
            missing_files = _missing_required_files(PACKAGE_DIR)
            if missing_files:
                for item in os.listdir(PACKAGE_DIR):
                    if item in protected:
                        continue
                    target = os.path.join(PACKAGE_DIR, item)
                    if os.path.isdir(target):
                        shutil.rmtree(target)
                    else:
                        os.remove(target)
                for item in os.listdir(backup_dir):
                    shutil.move(os.path.join(backup_dir, item), os.path.join(PACKAGE_DIR, item))
                shutil.rmtree(temp_dir)
                warn_red(
                    "Update looked incomplete (missing: " + ", ".join(missing_files) + "). "
                    "Restored your previous install untouched -- nothing was changed."
                )
                return

            # LICENSE / pyproject.toml live next to the package folder in
            # the repo (i.e. in zip_root, the wrapper folder), not inside
            # it -- copy them to PACKAGE_DIR's parent to match.
            install_root = os.path.dirname(str(PACKAGE_DIR))
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