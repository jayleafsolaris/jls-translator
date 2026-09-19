from ._protect import _protect


def tokens_only_diff(old_text, new_text):
    """
    Compares an old and new base value and checks whether the *only*
    difference between them lives inside protected tokens (%1$s-style
    placeholders, section-sign color codes, PUA glyphs, etc) -- i.e. every
    bit of actual translatable text is byte-for-byte identical, only the
    token(s) themselves changed (a swapped placeholder index, a different
    color code, and so on).

    Returns the new token list (in order) if that's the case, so the caller
    can splice it into an already-translated string instead of retranslating.
    Returns None if there's any other change (meaning a real retranslation
    is needed), including the case where nothing changed at all.
    """
    old_skeleton, old_tokens = _protect(old_text)
    new_skeleton, new_tokens = _protect(new_text)
    if old_skeleton != new_skeleton:
        return None
    if old_tokens == new_tokens:
        return None
    return new_tokens
