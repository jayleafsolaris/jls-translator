"""
Shared helpers for --split/--merge: splitting `base` into a folder
hierarchy along its "## " section headers, and rebuilding `base` from
that hierarchy again.

Only a line matching exactly TWO leading '#' characters followed by
whitespace counts as a section boundary (`## Name`). Deeper heading
levels (###, ####, #####) are treated as ordinary content and stay
verbatim inside whichever section's .txt file they fall under -- they
don't create their own folders or get split any further.

This also naturally excludes lines like
`##24175e243bcdb082a4fee9e61=13` (the --update run-count marker, see
state.py's _UPDATE_COUNT_MARKER) from being mistaken for a header,
since there's no whitespace directly after the '##' there.
"""

import json
import re

from .state import DEFAULTS, PACKAGE_DIR

_TOP_HEADER_RE = re.compile(r'^##[ \t]+(\S.*)$')
_UNSAFE_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


def sanitize_name(name):
    """Turn a '## Name' header's text into a safe folder/file name."""
    cleaned = _UNSAFE_CHARS_RE.sub("_", name).strip()
    return cleaned or "section"


def parse_sections(text):
    """
    Split `text` (the full contents of `base`) into an ordered list of
    (name, content) pairs, one per top-level '## Name' header. `content`
    is everything between that header and the next one (or EOF),
    verbatim -- including nested ###/####/##### headers, comments, and
    blank lines -- with no reformatting.

    Returns [] if there are no '##' headers at all. Raises ValueError if
    there's non-blank content before the first '##' header, since that
    content has nowhere sensible to go.
    """
    lines = text.splitlines(keepends=True)

    header_indices = []
    names = []
    for i, line in enumerate(lines):
        m = _TOP_HEADER_RE.match(line.rstrip("\r\n"))
        if m:
            header_indices.append(i)
            names.append(m.group(1).rstrip())

    if not header_indices:
        return []

    if header_indices[0] != 0:
        preamble = "".join(lines[:header_indices[0]]).strip()
        if preamble:
            raise ValueError(
                "found content before the first '##' header -- move it under a section first"
            )

    sections = []
    for idx, start in enumerate(header_indices):
        end = header_indices[idx + 1] if idx + 1 < len(header_indices) else len(lines)
        content = "".join(lines[start + 1:end])
        sections.append((names[idx], content))
    return sections


def render_sections(sections):
    """Inverse of parse_sections: reassemble (name, content) pairs into base's text."""
    parts = []
    for name, content in sections:
        parts.append(f"## {name}\n")
        parts.append(content)
    return "".join(parts)


def _section_order_path():
    return PACKAGE_DIR / DEFAULTS["section_order_cache"]


def load_section_order():
    """Returns the cached ordered list of folder names from the last --split, or None."""
    path = _section_order_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    order = data.get("order")
    return order if isinstance(order, list) else None


def save_section_order(order):
    """Persists the ordered list of folder names produced by --split, for --merge to read back."""
    path = _section_order_path()
    path.write_text(json.dumps({"order": order}, indent=2), encoding="utf-8")