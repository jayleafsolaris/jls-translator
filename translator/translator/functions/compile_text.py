import base64
import secrets
from ..common.obfuscate import _KEY_LEN
from ._marker_line import _marker_line
from ._xor_repeat import _xor_repeat


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
