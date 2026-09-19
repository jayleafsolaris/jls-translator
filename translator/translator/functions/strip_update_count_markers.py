from ._update_count_comment_prefix import _update_count_comment_prefix


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
