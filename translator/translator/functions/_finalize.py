def _finalize(node):
    """Splits node.content_raw into node.key_text (non-blank lines only) and
    node.blanks (positions + exact text of the blank lines removed from it),
    then recurses into children. Called once, after the whole file is parsed."""
    key_lines = []
    blanks = []
    for i, line in enumerate(node.content_raw):
        if line.strip() == "":
            blanks.append({"pos": i, "text": line})
        else:
            key_lines.append(line)
    node.key_text = "".join(key_lines)
    node.blanks = blanks
    for child in node.children:
        _finalize(child)
