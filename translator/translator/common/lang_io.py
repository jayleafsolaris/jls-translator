"""
Reading and writing .lang files, plus the hidden --update run-count
marker comment stored at the bottom of base.
"""

from pathlib import Path

from .state import _UPDATE_COUNT_MARKER

def parse_lang(path: Path):
    lines = []
    if not path.exists():
        return lines
    with path.open("r", encoding="utf-8") as f:
        for raw in f.read().splitlines():
            stripped = raw.strip()
            if not stripped:
                lines.append(("blank", ""))
                continue
            if stripped.startswith("#"):
                # Any line starting with '#' is a comment -- this covers
                # both '##'/'###' section headers and a single '#' used to
                # disable/comment-out an entry (e.g. '#ui.roe:key=value').
                # Without this, a single-'#' disabled entry that still
                # contains an '=' would otherwise fall through to the
                # entry-parsing branch below and get treated as a real key
                # (with a stray '#' stuck in front of it), which then
                # pollutes key counts, the cache, and generated .lang files.
                lines.append(("comment", raw))
                continue
            if "=" not in raw:
                lines.append(("comment", raw))
                continue
            key, _, rest = raw.partition("=")
            key = key.strip()
            inline_comment = None
            if "\t##" in rest:
                rest, _, inline_comment = rest.partition("\t##")
            lines.append(("entry", key, rest, inline_comment))
    return lines

def entries_dict(lines):
    return {l[1]: l[2] for l in lines if l[0] == "entry"}

def write_lang(path: Path, lines):
    out = []
    for line in lines:
        if line[0] == "blank":
            out.append("")
        elif line[0] == "comment":
            out.append(line[1])
        else:
            _, key, value, inline_comment = line
            if inline_comment is not None:
                out.append(f"{key}={value}\t##{inline_comment}")
            else:
                out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _update_count_comment_prefix():
    return f"##{_UPDATE_COUNT_MARKER}="


def read_update_count_from_base(base_lines):
    """
    Scans a base file's parsed lines for the hidden --update count marker
    comment and returns its integer value, or None if the marker isn't
    present (or is unparseable) in these lines.
    """
    prefix = _update_count_comment_prefix()
    for line in base_lines:
        if line[0] == "comment" and line[1].strip().startswith(prefix):
            try:
                return int(line[1].strip()[len(prefix):].strip())
            except ValueError:
                continue
    return None


def strip_update_count_markers(base_lines):
    """
    Returns base_lines with any existing --update count marker comment(s)
    removed. Used whenever base's lines are copied out into an actual
    .lang file (en_US.lang, translated output, etc) so the hidden marker
    never leaks into generated, user-facing files -- it only ever belongs
    at the bottom of base itself.
    """
    prefix = _update_count_comment_prefix()
    return [
        line for line in base_lines
        if not (line[0] == "comment" and line[1].strip().startswith(prefix))
    ]


def strip_comments_for_output(base_lines):
    """
    Returns base_lines with EVERY comment line removed -- section headers
    like '## UI' / '### PACK DETAILS', notes, and disabled/commented-out
    entries that start with a bare '#' -- plus the hidden --update count
    marker (which is itself stored as a comment, so it's covered by this
    too).

    Comments are organizational scaffolding for `base` only. They should
    never be copied into an actual, user-facing .lang file -- not the
    untranslated en_US/en_GB copies, and not the real translated
    languages. This is called on base's parsed lines before any of that
    copying happens; `base` itself is never touched by this function.
    """
    return [line for line in base_lines if line[0] != "comment"]


