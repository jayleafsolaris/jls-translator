from ..common.translate import _fallback_count


def get_fallback_count():
    """Total number of values that fell back to untranslated text (real
    outages aside) across the whole process so far. Exposed so callers
    like --update can fold this into their own live progress display
    instead of translate_many announcing it mid-run itself."""
    return _fallback_count
