from ..common.text_protect import BRITISH_SPELLINGS, _WORD_PATTERN
from ._match_case import _match_case
from ._protect import _protect
from ._restore import _restore


def to_british(text):
    if not text:
        return text
    protected, tokens = _protect(text)
    def repl(m):
        word = m.group(0)
        brit = BRITISH_SPELLINGS.get(word.lower())
        if brit is None:
            return word
        return _match_case(word, brit)
    converted = _WORD_PATTERN.sub(repl, protected)
    return _restore(converted, tokens)
