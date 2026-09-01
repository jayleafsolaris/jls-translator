from ..common.state import DEFAULTS, PACKAGE_DIR
from ._backup_path import _backup_path


def refresh_base_backup(script_dir):
    """
    If `base` currently exists as a plain file, snapshots its content.
    No-op if it's missing, or currently split into a base/ folder (there's
    nothing single-file to snapshot in that state -- the pre-split
    snapshot, taken right before --split deletes the file, already covers
    that transition).
    """
    base_path = script_dir / DEFAULTS["base_lang"]
    if base_path.is_file():
        try:
            _backup_path().write_text(base_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass  # best-effort -- a backup snapshot should never block the real command
