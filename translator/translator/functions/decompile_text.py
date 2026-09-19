from ..common.state import _COMPILE_KEY_MARKER
import base64
from ._xor_repeat import _xor_repeat


def decompile_text(text, key):
    """
    Inverse of compile_text. `key` must be the bytes returned by compile_text
    (see cache.load_compile_key). Raises ValueError if the marker is missing
    or the blob can't be decoded with the given key.
    """
    marker = f"##{_COMPILE_KEY_MARKER}"
    lines = text.splitlines()
    marker_idx = next((i for i, l in enumerate(lines) if l.startswith(marker)), None)
    if marker_idx is None:
        raise ValueError("no compile marker found -- this doesn't look like compiled base")

    blob = "\n".join(lines[:marker_idx]).strip()
    try:
        xored = base64.b64decode(blob.encode("ascii"))
        original = _xor_repeat(xored, key).decode("utf-8")
    except Exception:
        raise ValueError("couldn't decode compiled base -- it may be corrupted")

    return original
