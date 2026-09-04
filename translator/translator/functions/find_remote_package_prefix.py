def find_remote_package_prefix(tree_entries):
    """
    Scans a full recursive tree for wherever cli.py actually lives in the
    repo, and returns that directory as the path prefix everything else
    should be synced under ("" if cli.py sits at the repo root). Returns
    None if cli.py isn't found at all (unexpected repo layout).
    """
    for e in tree_entries:
        if e["type"] == "blob" and e["path"].rsplit("/", 1)[-1] == "cli.py":
            path = e["path"]
            return path.rsplit("/", 1)[0] if "/" in path else ""
    return None
