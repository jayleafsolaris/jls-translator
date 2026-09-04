from ._backup_path import _backup_path


def load_base_backup():
    """Returns the last snapshotted base content, or None if there isn't one."""
    path = _backup_path()
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None
