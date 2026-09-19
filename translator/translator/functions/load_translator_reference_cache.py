from ..common.state import PACKAGE_DIR, DEFAULTS
import json


def load_translator_reference_cache():
    """
    Returns {lang_code: {key: translated_value}} for every Translator
    Reference key (see lang_io.translator_reference_keys()) translated so
    far, for every language. These values never live inside any .lang
    file -- see lang_io.strip_translator_references() -- so this is their
    only persisted home, and the only way --update's otherwise
    file-driven incremental model can know one exists, notice its base
    text changed, or reuse it to resolve another entry's '{key.path}'
    cross-reference without retranslating it every single run.
    """
    path = PACKAGE_DIR / DEFAULTS["translator_reference_cache_file"]
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}
