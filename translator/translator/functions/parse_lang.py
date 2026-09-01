from pathlib import Path


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
