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
from ..functions._backup_path import _backup_path
from ..functions.load_base_backup import load_base_backup
from ..functions.refresh_base_backup import refresh_base_backup
