import os
import shutil
from ._contains_protected import _contains_protected


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
