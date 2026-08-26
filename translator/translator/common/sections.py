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

`base` must open with a single '##' heading (exactly two hashes) --
that's the root wrapper for everything under it (e.g. an addon's own
name). Any FURTHER '##' heading anywhere else in the document is not
special in any way -- it's just another heading, nested wherever it
appears, same as any '###'/'####'/etc. This is what lets someone fold a
second addon's lang into `base` just by dropping in another
'## SomeAddonName' heading somewhere.

The one real exception is the --update run-count marker (see state.py's
_UPDATE_COUNT_MARKER) -- a "##"-prefixed line with no space after the
hashes, e.g. `##24175e243bcdb082a4fee9e61=13`, conventionally sitting at
the very bottom of base. It never matches the heading pattern (no
whitespace after '##'), and on top of that it's explicitly recognized
and pulled out of the tree entirely here -- it's never attributed to any
section, never written into any keys.txt, and gets reappended verbatim
at the very end of the file on --merge.

Blank lines are also never written into a keys.txt -- each heading's
content is split into its actual (non-blank) lines for keys.txt, and a
separate positional record of exactly which lines were blank (and their
raw text). --merge splices those blank lines back into their original
positions, so the reassembled `base` is byte-for-byte identical to what
was split.
"""

import json
import re

from .state import DEFAULTS, PACKAGE_DIR, _UPDATE_COUNT_MARKER

_HEADER_RE = re.compile(r'^(#{2,})[ \t]+(\S.*)$')
_UNSAFE_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
_UPDATE_MARKER_PREFIX = f"##{_UPDATE_COUNT_MARKER}="

KEYS_FILENAME = "keys.txt"


def sanitize_name(name):
    """Turn a heading's text into a safe folder name."""
    cleaned = _UNSAFE_CHARS_RE.sub("_", name).strip()
    return cleaned or "section"


class Node:
    """One heading in the tree. The synthetic root (level=1, name=None) is
    never itself written out -- only its descendants are."""

    __slots__ = ("level", "name", "folder", "content_raw", "key_text", "blanks", "children")

    def __init__(self, level, name, folder):
        self.level = level
        self.name = name
        self.folder = folder
        self.content_raw = []   # raw lines under this heading, blanks/keys not yet separated
        self.key_text = ""      # filled in by _finalize(): the eventual keys.txt content
        self.blanks = []        # filled in by _finalize(): [{"pos": i, "text": raw_line}, ...]
        self.children = []      # list of Node, in source order


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


def parse_tree(text):
    """
    Parses `text` (the full contents of `base`) into a tree of Node
    objects, keyed off heading depth. Returns (root, markers):
    root.children are the real top-level sections, and markers is the
    list of raw --update run-count marker lines found anywhere in the
    file (almost always exactly one, at the very end).

    Raises ValueError if there's non-blank content before the very first
    heading, or if that very first heading isn't a single '##' (exactly
    two hashes).
    """
    lines = text.splitlines(keepends=True)
    root = Node(level=1, name=None, folder=None)
    stack = [root]
    first_header_seen = False
    preamble = []
    markers = []

    for line in lines:
        stripped = line.rstrip("\r\n")
        m = _HEADER_RE.match(stripped)
        if m:
            level = len(m.group(1))
            name = m.group(2).rstrip()
            if not first_header_seen:
                if level != 2:
                    raise ValueError(
                        f"base must start with a single '##' heading (found "
                        f"'{'#' * level} {name}' instead)"
                    )
                first_header_seen = True
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            node = Node(level=level, name=name, folder=sanitize_name(name))
            stack[-1].children.append(node)
            stack.append(node)
        elif stripped.startswith(_UPDATE_MARKER_PREFIX):
            markers.append(line)
        elif not first_header_seen:
            preamble.append(line)
        else:
            stack[-1].content_raw.append(line)

    if "".join(preamble).strip():
        raise ValueError(
            "found content before the first '##' heading -- move it under a section first"
        )

    _finalize(root)
    return root, markers


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
        if child.key_text.strip():
            paths.append(f"{child_prefix}/{KEYS_FILENAME}")
        paths.extend(preview_paths(child, child_prefix))
    return paths


def write_tree(node, folder_path):
    """Writes node's own keys.txt (if it has any non-blank content), then recurses into children."""
    if node.key_text.strip():
        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / KEYS_FILENAME).write_text(node.key_text, encoding="utf-8")
    for child in node.children:
        write_tree(child, folder_path / child.folder)


def _reconstruct_content(key_text, blanks):
    """Inverse of _finalize: splices the recorded blank lines back into their exact
    original positions among the keys.txt lines."""
    key_lines = key_text.splitlines(keepends=True) if key_text else []
    blank_map = {b["pos"]: b["text"] for b in blanks}
    total = len(key_lines) + len(blanks)
    parts = []
    ki = 0
    for i in range(total):
        if i in blank_map:
            parts.append(blank_map[i])
        else:
            parts.append(key_lines[ki])
            ki += 1
    return "".join(parts)


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
        parts.extend(markers)

    return "".join(parts)


def _node_to_dict(node):
    return {
        "level": node.level,
        "name": node.name,
        "folder": node.folder,
        "blanks": node.blanks,
        "children": [_node_to_dict(c) for c in node.children],
    }


def _section_data_path():
    return PACKAGE_DIR / DEFAULTS["section_order_cache"]


def save_section_data(root_children, markers):
    """Persists the tree shape (headings, levels, nesting, blank-line positions) and
    the --update marker line(s), for --merge to read back."""
    data = {
        "tree": [_node_to_dict(n) for n in root_children],
        "markers": markers,
    }
    _section_data_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


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