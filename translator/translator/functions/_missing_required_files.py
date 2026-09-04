import os
from ..modes.upgrade import _REQUIRED_PACKAGE_FILES


def _missing_required_files(package_root):
    return [f for f in _REQUIRED_PACKAGE_FILES if not os.path.isfile(os.path.join(package_root, f))]
