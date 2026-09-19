from ..common.text_protect import _SPLIT_PATTERN


def split_segments(text):
    """
    Splits text into an ordered list of ('token', literal) / ('text', content)
    pieces at TOKEN_PATTERN boundaries (color codes, %1$s-style
    placeholders, {key.path} cross-references, __NL__ newline markers, PUA
    glyphs).

    Unlike _protect(), this does NOT substitute tokens with an opaque
    marker that then travels alongside real text -- it separates them out
    entirely. Callers should send ONLY the 'text' pieces to a translation
    service and pass 'token' pieces through completely untouched, so a
    translator never sees anything but genuine human-readable language
    (no placeholder-shaped noise mixed in that could get mistranslated or
    read as spam/repetition).

    Empty text pieces (two tokens with nothing between them) are omitted
    entirely, since join_segments()/straight concatenation reconstructs
    correctly either way.
    """
    raw = _SPLIT_PATTERN.split(text)
    parts = []
    for i, chunk in enumerate(raw):
        if i % 2 == 1:
            parts.append(("token", chunk))
        elif chunk:
            parts.append(("text", chunk))
    return parts
