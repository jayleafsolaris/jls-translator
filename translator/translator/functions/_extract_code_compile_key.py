from ..common.state import _CLI_KEY_TAG


def _extract_code_compile_key(cli_py_text):
    """
    Pulls the hidden code-compile key out of a cli.py file's own source
    text -- a plain trailing "##<tag>:<hex>" comment line rather than an
    obviously-named constant, so it doesn't read as "here is the secret"
    to a casual skim the way `_CODE_COMPILE_KEY = "..."` would (see
    cli.py's own comment). --push rotates it to a brand new random key
    on every single push (see _set_hidden_code_key.py) and rewrites this
    same line with the new one; this is how --pull/--upgrade recover
    whichever key the fetched/downloaded cli.py was actually pushed
    with, without any separate distribution or local caching.

    Searches from the end since the line is meant to be trailing, and
    naturally prefers the LAST such line if more than one somehow exists.
    Returns the key as bytes, or None if cli.py's text has no such line
    at all (a version from before this feature existed, or corrupted).
    """
    tag_prefix = f"##{_CLI_KEY_TAG}:"
    for line in reversed(cli_py_text.splitlines()):
        if line.startswith(tag_prefix):
            hex_part = line[len(tag_prefix):].strip()
            if len(hex_part) != 64:
                return None
            try:
                return bytes.fromhex(hex_part)
            except ValueError:
                return None
    return None
