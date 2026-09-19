from ._update_count_comment_prefix import _update_count_comment_prefix


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
