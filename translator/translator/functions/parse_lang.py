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
