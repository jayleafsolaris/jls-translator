from ..common.state import _CODE_COMPILE_KEY_MARKER


def is_compiled_code(text):
    return f"##{_CODE_COMPILE_KEY_MARKER}" in text
