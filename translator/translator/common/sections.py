"""
Shared helpers for --split/--merge: turning `base` into a nested folder
hierarchy that mirrors EVERY heading depth ('##', '###', '####', ...),
and rebuilding `base` from that hierarchy again.

Any line matching '#'*2-or-more followed by whitespace is a heading, and
its hash count is its depth. Each heading becomes a folder named after
its (sanitized) text, nested inside its parent heading's folder. A
heading's own content -- the lines that appear directly under it, before
its first child heading -- is written as that folder's `keys.txt`. A
heading with no content of its own (just child headings) gets no
keys.txt, only subfolders.

Example, given:

    ## UI
    ### PACK DETAILS
    ui.roe:pack.name

--split produces (base/ being the top-level replacement for the base
file itself):

    base/UI/PACK DETAILS/keys.txt      <- contains "ui.roe:pack.name"

This also naturally excludes lines like
`##24175e243bcdb082a4fee9e61=13` (the --update run-count marker, see
state.py's _UPDATE_COUNT_MARKER) from being mistaken for a heading,
since there's no whitespace directly after the '##' there.
"""

import json
import re

from .state import DEFAULTS, PACKAGE_DIR

_HEADER_RE = re.compile(r'^(#{2,})[ \t]+(\S.*)$')
_UNSAFE_CHARS_RE = re.compile(r'[\\/:*?"<>|]')

KEYS_FILENAME = "keys.txt"


def sanitize_name(name):
    """Turn a heading's text into a safe folder name."""
    cleaned = _UNSAFE_CHARS_RE.sub("_", name).strip()
    return cleaned or "section"


class Node:
    """One heading in the tree. The synthetic root (level=1, name=None) is
    never itself written out -- only its descendants are."""

    __slots__ = ("level", "name", "folder", "content", "children")

    def __init__(self, level, name, folder):
        self.level = level
        self.name = name
        self.folder = folder
        self.content = ""       # this heading's own lines (before any child heading)
        self.children = []      # list of Node, in source order


def parse_tree(text):
    """
    Parses `text` (the full contents of `base`) into a tree of Node
    objects, keyed off heading depth. Returns the synthetic root Node;
    real top-level sections are root.children.

    Raises ValueError if there's non-blank content before the very first
    heading, since that content has no heading to belong to.
    """
    lines = text.splitlines(keepends=True)
    root = Node(level=1, name=None, folder=None)
    stack = [root]
    first_header_seen = False
    preamble = []

    for line in lines:
        m = _HEADER_RE.match(line.rstrip("\r\n"))
        if m:
            first_header_seen = True
            level = len(m.group(1))
            name = m.group(2).rstrip()
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            node = Node(level=level, name=name, folder=sanitize_name(name))
            stack[-1].children.append(node)
            stack.append(node)
        elif not first_header_seen:
            preamble.append(line)
        else:
            stack[-1].content += line

    if "".join(preamble).strip():
        raise ValueError(
            "found content before the first '##' heading -- move it under a section first"
        )

    return root


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


def preview_paths(node, prefix):
    """Returns the list of keys.txt paths --split would write, for confirmation prompts."""
    paths = []
    for child in node.children:
        child_prefix = f"{prefix}/{child.folder}"
        if child.content.strip():
            paths.append(f"{child_prefix}/{KEYS_FILENAME}")
        paths.extend(preview_paths(child, child_prefix))
    return paths


def write_tree(node, folder_path):
    """Writes node's own content (if any) as folder_path/keys.txt, then recurses into children."""
    if node.content.strip():
        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / KEYS_FILENAME).write_text(node.content, encoding="utf-8")
    for child in node.children:
        write_tree(child, folder_path / child.folder)


def render_tree(tree, base_dir):
    """
    Inverse of write_tree + save_section_tree: given the cached tree
    (list of node-dicts, see _node_to_dict) and the base/ folder they
    were written under, reassembles base's full text.
    """
    parts = []

    def _walk(node_dict, dir_path):
        parts.append("#" * node_dict["level"] + " " + node_dict["name"] + "\n")
        keys_file = dir_path / KEYS_FILENAME
        if keys_file.exists():
            parts.append(keys_file.read_text(encoding="utf-8"))
        for child in node_dict["children"]:
            _walk(child, dir_path / child["folder"])

    for node_dict in tree:
        _walk(node_dict, base_dir / node_dict["folder"])

    return "".join(parts)


def _node_to_dict(node):
    return {
        "level": node.level,
        "name": node.name,
        "folder": node.folder,
        "children": [_node_to_dict(c) for c in node.children],
    }


def _section_tree_path():
    return PACKAGE_DIR / DEFAULTS["section_order_cache"]


def save_section_tree(root_children):
    """Persists the tree shape (headings, levels, nesting -- not their content) for --merge."""
    data = {"tree": [_node_to_dict(n) for n in root_children]}
    _section_tree_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_section_tree():
    """Returns the cached tree (list of node-dicts) from the last --split, or None."""
    path = _section_tree_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    tree = data.get("tree")
    return tree if isinstance(tree, list) else None