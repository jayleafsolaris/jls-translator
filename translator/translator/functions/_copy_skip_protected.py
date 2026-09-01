import os
import shutil


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
