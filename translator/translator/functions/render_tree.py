from ..common.sections import KEYS_FILENAME
from ._reconstruct_content import _reconstruct_content


def render_tree(tree, base_dir, markers=None):
    """
    Inverse of write_tree + save_section_data: given the cached tree
    (list of node-dicts, see _node_to_dict), the base/ folder they were
    written under, and the cached marker lines, reassembles base's full
    text -- blank lines restored in place, marker line(s) reappended at
    the very end.
    """
    parts = []

    def _walk(node_dict, dir_path):
        parts.append("#" * node_dict["level"] + " " + node_dict["name"] + "\n")
        keys_file = dir_path / KEYS_FILENAME
        key_text = keys_file.read_text(encoding="utf-8") if keys_file.exists() else ""
        parts.append(_reconstruct_content(key_text, node_dict.get("blanks", [])))
        for child in node_dict["children"]:
            _walk(child, dir_path / child["folder"])

    for node_dict in tree:
        _walk(node_dict, base_dir / node_dict["folder"])

    if markers:
        # The marker(s) need their own line. Normally the last reconstructed
        # content already ends in "\n" (that's what separated it from the
        # marker in the original file), but a keys.txt someone hand-edited
        # can lose its trailing newline (many editors strip/skip it on
        # save) -- without this check the marker would get glued directly
        # onto the last value instead of the newline being restored.
        if parts and not parts[-1].endswith("\n"):
            parts.append("\n")
        parts.extend(markers)

    return "".join(parts)
