import re
from ._protect import _protect

# Deliberately excludes "@" so a protected token sitting right at the very
# edge of the skeleton (e.g. "@@PH0@@!" or "(@@PH0@@") is never mistaken
# for punctuation -- the run stops at the placeholder marker's boundary.
_LEADING_PUNCT_RE = re.compile(r"^[^\w@]*")
_TRAILING_PUNCT_RE = re.compile(r"[^\w@]*$")


def punctuation_only_diff(old_text, new_text):
    """
    Like tokens_only_diff, but for punctuation at the very start and/or
    end of a base value -- a trailing "!" added to a heading, a "."
    swapped for a "?", a leading quote mark dropped, an ellipsis added
    where there was no punctuation at all before, and so on.

    Compares old and new base text (with protected tokens -- %1$s-style
    placeholders, color codes, etc -- pulled out first, same as
    tokens_only_diff) and checks whether the *only* difference is the
    leading and/or trailing punctuation run, with every token identical
    and in the same order, and everything in between byte-for-byte the
    same.

    Returns (old_leading, old_trailing, new_leading, new_trailing) if
    that's the case, so the caller can strip the OLD edge punctuation off
    an already-translated string (apply_punctuation_patch expects exactly
    these four pieces) and splice the new pair on instead, without
    sending anything to Google Translate. Returns None if there's any
    other change -- meaning a real retranslation is needed, or a token
    also changed (that's tokens_only_diff's job), or nothing changed at
    all.
    """
    old_skeleton, old_tokens = _protect(old_text)
    new_skeleton, new_tokens = _protect(new_text)
    if old_tokens != new_tokens:
        return None

    old_lead = _LEADING_PUNCT_RE.match(old_skeleton).group(0)
    new_lead = _LEADING_PUNCT_RE.match(new_skeleton).group(0)
    old_rest = old_skeleton[len(old_lead):]
    new_rest = new_skeleton[len(new_lead):]

    old_trail = _TRAILING_PUNCT_RE.search(old_rest).group(0)
    new_trail = _TRAILING_PUNCT_RE.search(new_rest).group(0)
    old_core = old_rest[:len(old_rest) - len(old_trail)]
    new_core = new_rest[:len(new_rest) - len(new_trail)]

    if old_core != new_core:
        return None
    if old_lead == new_lead and old_trail == new_trail:
        return None
    return old_lead, old_trail, new_lead, new_trail
