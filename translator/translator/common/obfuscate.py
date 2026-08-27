"""
Shared helpers for --compile/--decompile: a lightweight, fully-reversible
obfuscation of `base`'s raw text, keyed by a fresh random key every time
--compile runs. The key is cached (see common/cache.py's save_compile_key/
load_compile_key) rather than stored in base itself -- base only keeps a
flag marker line so is_compiled() can tell compiled from plain text.
The marker is a "##"-prefixed line with no space after the hashes, in the
same spirit as state.py's _UPDATE_COUNT_MARKER, so it's never mistaken for
a real '## Name' heading (see common/sections.py's _HEADER_RE).

This is obfuscation, not encryption -- it exists to make a distributed
`base` file not trivially diffable/readable at a glance, not to protect
it against anyone willing to read this source.
"""

import base64
import secrets

from .state import _COMPILE_KEY_MARKER

_KEY_LEN = 32  # bytes -- fresh random key every --compile run


def _xor_repeat(data, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _marker_line():
    return f"##{_COMPILE_KEY_MARKER}\n"


def is_compiled(text):
    return f"##{_COMPILE_KEY_MARKER}" in text


def compile_text(text):
    """
    Returns (obfuscated_text, key) -- a fresh random key each call. The key
    is no longer embedded in the text; the caller is responsible for
    caching it (see cache.save_compile_key).
    """
    key = secrets.token_bytes(_KEY_LEN)
    xored = _xor_repeat(text.encode("utf-8"), key)
    blob = base64.b64encode(xored).decode("ascii")
    return blob + "\n" + _marker_line(), key


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