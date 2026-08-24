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

        shutil.rmtree(temp_dir)
        print(f"Update complete!")
        if skipped:
            print(f"Left your local cache/config untouched (repo also had: {', '.join(sorted(skipped))}).")
        
        # Strip --upgrade from args so it doesn't loop infinitely upon restart
        new_args = [arg for arg in sys.argv if arg != "--upgrade"]
        if len(new_args) == 1:
            new_args.append("--version") # Just show the version if they ran it raw
            
        os.execv(sys.executable, [sys.executable] + new_args)
        
    except Exception as e:
        warn_red(f"Update failed: {e}")