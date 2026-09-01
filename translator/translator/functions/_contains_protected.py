import os


def _contains_protected(dir_path, protected):
    """True if dir_path contains a protected-named file/folder anywhere below it."""
    for dirpath, dirnames, filenames in os.walk(dir_path):
        for name in dirnames + filenames:
            if name in protected:
                return True
    return False
