"""
Shared helpers for --compile/--decompile: a lightweight, fully-reversible
obfuscation of `base`'s raw text, keyed by a fresh random key every time
--compile runs. The key needed to reverse it is stored in a trailing
"##"-prefixed marker line, in the same spirit as state.py's
_UPDATE_COUNT_MARKER -- a "##" line with no space after the hashes,
so it's never mistaken for a real '## Name' heading (see
common/sections.py's _HEADER_RE) and is otherwise just an opaque
trailing comment as far as everything else in this tool is concerned.

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


def _marker_line(key):
    return f"##{_COMPILE_KEY_MARKER}={key.hex()}\n"


def is_compiled(text):
    return f"##{_COMPILE_KEY_MARKER}=" in text


def compile_text(text):
    """Returns a freshly-obfuscated version of `text`, with a new random key each call."""
    key = secrets.token_bytes(_KEY_LEN)
    xored = _xor_repeat(text.encode("utf-8"), key)
    blob = base64.b64encode(xored).decode("ascii")
    return blob + "\n" + _marker_line(key)


def decompile_text(text):
    """Inverse of compile_text. Raises ValueError if no valid marker is found."""
    marker_prefix = f"##{_COMPILE_KEY_MARKER}="
    lines = text.splitlines()
    marker_idx = next((i for i, l in enumerate(lines) if l.startswith(marker_prefix)), None)
    if marker_idx is None:
        raise ValueError("no compile key marker found -- this doesn't look like compiled base")

    key_hex = lines[marker_idx][len(marker_prefix):].strip()
    try:
        key = bytes.fromhex(key_hex)
    except ValueError:
        raise ValueError("compile key marker is present but malformed")

    blob = "\n".join(lines[:marker_idx]).strip()
    try:
        xored = base64.b64decode(blob.encode("ascii"))
        original = _xor_repeat(xored, key).decode("utf-8")
    except Exception:
        raise ValueError("couldn't decode compiled base -- it may be corrupted")

    return original