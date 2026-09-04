from ..common.state import _CLI_KEY_TAG


def _set_hidden_code_key(cli_py_text, key):
    """
    Returns cli_py_text with any existing hidden key marker line (see
    _extract_code_compile_key.py) removed and a fresh trailing one
    appended for `key` -- used by --push to rotate cli.py's embedded key
    to a brand new random one on every single push. A plain "##<tag>:<hex>"
    comment line, not a named constant, so it doesn't read as "here is
    the secret" at a glance (see cli.py's own comment).
    """
    tag_prefix = f"##{_CLI_KEY_TAG}:"
    lines = [l for l in cli_py_text.splitlines() if not l.startswith(tag_prefix)]
    # Strip trailing blank lines so the marker sits right after real
    # content instead of floating after a growing gap of empty lines
    # every time this rewrites the file.
    while lines and lines[-1].strip() == "":
        lines.pop()
    lines.append(f"{tag_prefix}{key.hex()}")
    return "\n".join(lines) + "\n"
