def find_duplicate_siblings(node, path=""):
    """
    Returns a list of human-readable strings describing any set of
    sibling headings (same parent) that sanitize to the same folder
    name -- these would silently collide/overwrite each other on disk.
    """
    problems = []
    by_folder = {}
    for child in node.children:
        by_folder.setdefault(child.folder, []).append(child.name)
    for folder, names in by_folder.items():
        if len(names) > 1:
            where = f"{path}/{folder}" if path else folder
            problems.append(f"{where} <- {', '.join(names)}")
    for child in node.children:
        child_path = f"{path}/{child.folder}" if path else child.folder
        problems.extend(find_duplicate_siblings(child, child_path))
    return problems
