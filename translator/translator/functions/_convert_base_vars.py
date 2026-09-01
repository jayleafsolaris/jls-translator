import re


def _convert_base_vars(lines):
    """Converts user-friendly {1} syntax in base to Bedrock's %1$s."""
    out = []
    for line in lines:
        if line[0] == "entry":
            # Replaces {1} -> %1$s, {2} -> %2$s, etc.
            new_val = re.sub(r"\{(\d+)\}", r"%\1$s", line[2])
            out.append(("entry", line[1], new_val, line[3]))
        else:
            out.append(line)
    return out
