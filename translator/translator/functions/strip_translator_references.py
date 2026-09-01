def strip_translator_references(lines, ref_keys):
    """
    Returns `lines` with any ('entry', key, ...) line whose key is in
    ref_keys dropped entirely -- everything else (blanks, comments,
    every other entry) passes through unchanged.

    Call this right before every write_lang() of a real, user-facing
    .lang file (never on `base` itself). Translator Reference entries
    (see translator_reference_keys()) are translated like any other
    entry so cross-references resolve correctly, but should never appear
    as a key of their own in generated output -- this is the one place
    that's actually enforced, so it's cheap to also call defensively on
    any output built from a possibly-stale physical .lang file that
    predates this feature (self-heals a leftover leaked entry on its
    next write instead of needing a separate one-off cleanup pass).
    """
    if not ref_keys:
        return lines
    return [line for line in lines if not (line[0] == "entry" and line[1] in ref_keys)]
