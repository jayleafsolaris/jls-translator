from ..common.state import _CODE_COMPILE_KEY_MARKER
import base64
import hashlib
from ._xor_repeat import _xor_repeat


def decompile_code_text(text, key):
    """
    Inverse of compile_code_text(). `key` is normally whatever
    functions/_extract_code_compile_key.py pulled out of the relevant
    cli.py. Raises ValueError if the marker is missing,
    the blob can't be decoded with the given key, or the embedded
    checksum doesn't match -- the last case is what catches a wrong key
    that otherwise happens to decode as plausible-looking UTF-8 garbage
    (see compile_code_text()'s docstring for why that check exists here
    but not on base's equivalent).
    """
    marker = f"##{_CODE_COMPILE_KEY_MARKER}"
    lines = text.splitlines()
    marker_idx = next((i for i, l in enumerate(lines) if l.startswith(marker)), None)
    if marker_idx is None:
        raise ValueError("no code-compile marker found -- this doesn't look like compiled source")
    if marker_idx < 1:
        raise ValueError("couldn't decode compiled source -- it may be corrupted")

    checksum = lines[marker_idx - 1].strip()
    blob = "\n".join(lines[:marker_idx - 1]).strip()
    try:
        xored = base64.b64decode(blob.encode("ascii"))
        original = _xor_repeat(xored, key).decode("utf-8")
    except Exception:
        raise ValueError("couldn't decode compiled source -- it may be corrupted")

    if hashlib.sha256(original.encode("utf-8")).hexdigest()[:8] != checksum:
        raise ValueError("decompiled content failed its integrity check -- wrong key, or corrupted")

    return original
