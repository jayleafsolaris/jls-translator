from ._translate_segments_deferred import _translate_segments_deferred


def translate_value(google_code, text):
    """
    Translates a single string in isolation (for any caller working with
    just one string outside a translate_many() batch). Delegates to the
    same deferred-retry machinery translate_many's batch fallback uses --
    see _translate_segments_deferred -- though with only one item in the
    pool there's nothing else to interleave with, so a failing value
    simply retries itself up to DEFAULTS['max_retries'] times before
    falling back to the original text.
    """
    if not text.strip():
        return text
    return _translate_segments_deferred(google_code, [text])[text]
