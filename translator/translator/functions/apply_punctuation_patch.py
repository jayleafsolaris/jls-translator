def apply_punctuation_patch(translated_text, old_leading, old_trailing, new_leading, new_trailing):
    """
    Re-applies an updated leading/trailing punctuation pair onto an
    already-translated string without calling Google Translate. Only
    safe when the translated string still carries the exact OLD
    leading/trailing punctuation that punctuation_only_diff() saw on
    base -- translators don't always preserve edge punctuation
    byte-for-byte (curly quotes, added/dropped spacing, a mark that
    just gets absorbed into the sentence), so the caller should fall
    back to a full retranslation whenever this returns None.
    """
    core = translated_text
    if old_leading:
        if not core.startswith(old_leading):
            return None
        core = core[len(old_leading):]
    if old_trailing:
        if not core.endswith(old_trailing):
            return None
        core = core[:len(core) - len(old_trailing)]
    return f"{new_leading}{core}{new_trailing}"
