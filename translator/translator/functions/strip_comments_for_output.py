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
