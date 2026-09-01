from pathlib import Path


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
