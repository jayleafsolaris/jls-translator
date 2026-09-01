import re


def _parse_version_tuple(version_string):
    """
    Best-effort parse of a dotted version string into a tuple of ints for
    comparison (e.g. '1.5.10' -> (1, 5, 10)), ignoring any non-numeric
    suffix on a segment (e.g. '2rc1' -> 2) so odd version strings don't
    blow up the comparison.
    """
    parts = []
    for chunk in version_string.split("."):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group(0)) if m else 0)
    return tuple(parts)
