from ..common.translate import _fallback_lock, _fallback_log


def get_fallback_log():
    """Copy of the (preview, error) pairs behind get_fallback_count(), for
    callers that want to report specifics at the end of a run."""
    with _fallback_lock:
        return list(_fallback_log)
