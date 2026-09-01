"""
Reading and writing .lang files, plus the hidden --update run-count
marker comment stored at the bottom of base.
"""
from pathlib import Path
from .state import _UPDATE_COUNT_MARKER
from ..functions._update_count_comment_prefix import _update_count_comment_prefix
from ..functions.entries_dict import entries_dict
from ..functions.parse_lang import parse_lang
from ..functions.read_update_count_from_base import read_update_count_from_base
from ..functions.strip_comments_for_output import strip_comments_for_output
from ..functions.strip_update_count_markers import strip_update_count_markers
from ..functions.translator_reference_keys import translator_reference_keys
from ..functions.strip_translator_references import strip_translator_references
from ..functions.write_lang import write_lang
