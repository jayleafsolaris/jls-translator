import base64
import hashlib
from ._code_marker_line import _code_marker_line
from ._xor_repeat import _xor_repeat


def compile_code_text(text, key):
    """
    Same reversible XOR+base64 obfuscation as functions/compile_text.py
    uses for `base`, but for a single .py source file and keyed by an
    EXISTING key (the one embedded in cli.py -- see cli.py's own
    comment) rather than generating a fresh one each call, so compiling
    the same file twice with the same key produces identical ciphertext
    -- needed so --push's "unchanged file, skip re-upload" check
    (comparing git blob shas) actually works.

    Also embeds a short checksum of the original plaintext (unlike
    base's version). Plain XOR has no way to detect a wrong key on its
    own -- garbage bytes XORed with the wrong key can still happen to
    decode as valid UTF-8, silently "succeeding" with the wrong content.
    For `base` that's a minor annoyance; for this, --upgrade installs
    whatever comes out of decompiling as the tool's actual running code,
    so a wrong-key false-positive needs to be reliably catchable instead
    of shipping garbage with no warning.
    """
    xored = _xor_repeat(text.encode("utf-8"), key)
    blob = base64.b64encode(xored).decode("ascii")
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{blob}\n{checksum}\n" + _code_marker_line()
