from ..common.sections import _UNSAFE_CHARS_RE


def sanitize_name(name):
    """Turn a heading's text into a safe folder name."""
    cleaned = _UNSAFE_CHARS_RE.sub("_", name).strip()
    return cleaned or "section"
