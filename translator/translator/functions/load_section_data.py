import json
from ._section_data_path import _section_data_path


def load_section_data():
    """Returns (tree, markers) from the last --split, or None if there's no usable cache."""
    path = _section_data_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    tree = data.get("tree")
    if not isinstance(tree, list):
        return None
    markers = data.get("markers")
    if not isinstance(markers, list):
        markers = []
    return tree, markers
