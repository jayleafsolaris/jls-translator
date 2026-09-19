import json
from ._node_to_dict import _node_to_dict
from ._section_data_path import _section_data_path


def save_section_data(root_children, markers):
    """Persists the tree shape (headings, levels, nesting, blank-line positions) and
    the --update marker line(s), for --merge to read back."""
    data = {
        "tree": [_node_to_dict(n) for n in root_children],
        "markers": markers,
    }
    _section_data_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
