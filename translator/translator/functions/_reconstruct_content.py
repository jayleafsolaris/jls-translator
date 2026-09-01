def _reconstruct_content(key_text, blanks):
    """Inverse of _finalize: splices the recorded blank lines back into their exact
    original positions among the keys.txt lines."""
    key_lines = key_text.splitlines(keepends=True) if key_text else []
    blank_map = {b["pos"]: b["text"] for b in blanks}
    total = len(key_lines) + len(blanks)
    parts = []
    ki = 0
    for i in range(total):
        if i in blank_map:
            parts.append(blank_map[i])
        else:
            parts.append(key_lines[ki])
            ki += 1
    return "".join(parts)
