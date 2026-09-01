import os
import shutil


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
