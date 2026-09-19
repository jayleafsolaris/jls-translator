from ..common.sections import KEYS_FILENAME


def preview_paths(node, prefix):
    """Returns the list of keys.txt paths --split would write, for confirmation prompts."""
    paths = []
    for child in node.children:
        child_prefix = f"{prefix}/{child.folder}"
        if child.key_text.strip():
            paths.append(f"{child_prefix}/{KEYS_FILENAME}")
        paths.extend(preview_paths(child, child_prefix))
    return paths
