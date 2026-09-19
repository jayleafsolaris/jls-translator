import os
import shutil
from ._contains_protected import _contains_protected


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
