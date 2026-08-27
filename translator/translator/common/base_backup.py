"""
A dumb, always-on safety net for `base`: a last-known-good snapshot of
its raw content, refreshed on every single run of the tool (before AND
after whatever command actually executes), so that if `base` ever goes
missing -- hand-deleted, wiped by a bad mirror op, whatever -- there's
always something to offer restoring from.

This doesn't try to tell "good" content from "bad" content, and it isn't
scoped per-project -- it just remembers whatever `base` looked like the
last time ANY command saw it as a plain file, same sharing caveat as the
translation cache and section-order cache (see state.py's PACKAGE_DIR
comment). If you bounce between multiple projects with one install, only
the most recently touched project's `base` is backed up here.
"""

from .state import DEFAULTS, PACKAGE_DIR


def _backup_path():
    return PACKAGE_DIR / DEFAULTS["base_backup_file"]


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


def load_base_backup():
    """Returns the last snapshotted base content, or None if there isn't one."""
    path = _backup_path()
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None
