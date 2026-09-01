from ..common.sections import _HEADER_RE
from ..common.state import DEFAULTS


def translator_reference_keys(base_lines, section_name=None):
    """
    Returns the set of entry keys in `base_lines` that fall anywhere
    under a heading (at any depth) whose text matches
    DEFAULTS['translator_reference_section'] (case-insensitive), up
    until the next heading at that same or a shallower level.

    These keys exist in `base` purely to be translated and made
    available to OTHER entries' '{key.path}' cross-references (see
    text_protect.resolve_key_references) -- e.g. a shared "Blueprint"
    entry that several item names splice in via '{ui.index:blueprint}'
    so it's translated once, consistently, instead of duplicated
    verbatim in every entry that needs it. They're real, translated
    entries like any other -- just never meant to become a key of their
    own in any generated .lang file (see strip_translator_references()).
    """
    if section_name is None:
        section_name = DEFAULTS["translator_reference_section"]
    target = section_name.strip().lower()

    keys = set()
    target_level = None  # heading level of the currently-open target section, if inside one
    for line in base_lines:
        if line[0] == "comment":
            m = _HEADER_RE.match(line[1].strip())
            if m:
                level = len(m.group(1))
                name = m.group(2).strip()
                if target_level is not None and level <= target_level:
                    target_level = None  # left the target section (sibling or higher heading)
                if target_level is None and name.lower() == target:
                    target_level = level
            continue
        if line[0] == "entry" and target_level is not None:
            keys.add(line[1])
    return keys
