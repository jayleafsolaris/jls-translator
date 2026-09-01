from ..common.sections import Node, _HEADER_RE, _UPDATE_MARKER_PREFIX
from ._finalize import _finalize
from .sanitize_name import sanitize_name


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
    after_marker = False
    preamble = []
    markers = []

    for line in lines:
        if after_marker:
            # Once the first marker line is seen, everything past it --
            # additional marker lines, and any trailing blank line(s) some
            # editors/people leave at the very end of the file -- belongs
            # after the marker(s), not to whatever section happened to be
            # open. Otherwise a trailing blank line ends up misattributed
            # as that section's content and reappears in the wrong place
            # (before the marker instead of after it) on --merge.
            markers.append(line)
            continue
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
            after_marker = True
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
