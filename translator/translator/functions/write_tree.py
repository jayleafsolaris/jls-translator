from ..common.sections import KEYS_FILENAME


def write_tree(node, folder_path):
    """Writes node's own keys.txt (if it has any non-blank content), then recurses into children."""
    if node.key_text.strip():
        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / KEYS_FILENAME).write_text(node.key_text, encoding="utf-8")
    for child in node.children:
        write_tree(child, folder_path / child.folder)
