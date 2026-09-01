from ..common.state import _COMPILE_KEY_MARKER


def is_compiled(text):
    return f"##{_COMPILE_KEY_MARKER}" in text
