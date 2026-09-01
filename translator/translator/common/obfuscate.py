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
from ..functions._marker_line import _marker_line
from ..functions._xor_repeat import _xor_repeat
from ..functions.compile_text import compile_text
from ..functions.decompile_text import decompile_text
from ..functions.is_compiled import is_compiled
