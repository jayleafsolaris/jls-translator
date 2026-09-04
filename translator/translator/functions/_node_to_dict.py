def _node_to_dict(node):
    return {
        "level": node.level,
        "name": node.name,
        "folder": node.folder,
        "blanks": node.blanks,
        "children": [_node_to_dict(c) for c in node.children],
    }
