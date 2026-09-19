"""--apply: resolve {key.path} cross-references into every active .lang
file. Local text substitution only -- no translation, no network."""
from ..common import state
from ..common.cache import load_translator_reference_cache, save_translator_reference_cache, get_active_language_codes
from ..common.lang_io import parse_lang, write_lang, translator_reference_keys, strip_translator_references
from ..common.progress import load_base, format_duration, SmoothProgress, _report_applying
from ..common.state import LANGUAGES
from ..common.text_protect import resolve_key_references
from ..functions.cmd_apply import cmd_apply
