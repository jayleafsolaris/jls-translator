from ._protect import _protect
from ._restore import _restore


def apply_token_patch(translated_text, new_tokens):
    """
    Re-applies an updated token list onto an already-translated string
    without calling Google Translate. Only safe when the translated string
    contains the same number of protected tokens as the new base value --
    otherwise we can't line them up positionally, so the caller should fall
    back to a full retranslation. Returns None in that mismatch case.
    """
    skeleton, current_tokens = _protect(translated_text)
    if len(current_tokens) != len(new_tokens):
        return None
    return _restore(skeleton, new_tokens)
