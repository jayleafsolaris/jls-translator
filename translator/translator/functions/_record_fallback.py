from ..common.translate import _fallback_count, _fallback_lock, _fallback_log


def _record_fallback(preview, err):
    global _fallback_count
    with _fallback_lock:
        _fallback_count += 1
        _fallback_log.append((preview, err))
