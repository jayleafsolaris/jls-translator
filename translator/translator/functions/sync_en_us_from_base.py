from ..common import state
from ..common.lang_io import parse_lang, write_lang, strip_comments_for_output


def sync_en_us_from_base(base_lines):
    en_us_path = state.SCRIPT_DIR / "en_US.lang"
    # Strip every comment line (section headers, notes, disabled/commented
    # entries, and the hidden --update count marker) before mirroring base
    # into en_US.lang -- comments belong to base only and should never
    # show up in a generated, user-facing .lang file.
    write_lang(en_us_path, strip_comments_for_output(list(base_lines)))
    return en_us_path
