"""
Placeholder/token protection (so color codes and %1$s-style format specs
survive translation untouched) and the American -> British spelling
conversion used for en_GB.
"""

import re

from .state import TOKEN_PATTERN

def _protect(text):
    tokens = []
    def repl(m):
        tokens.append(m.group(0))
        return f"@@PH{len(tokens) - 1}@@"
    return TOKEN_PATTERN.sub(repl, text), tokens

def _restore(text, tokens):
    def repl(m):
        idx = int(m.group(1))
        return tokens[idx] if idx < len(tokens) else m.group(0)
    return re.sub(r"@\s*@\s*PH\s*(\d+)\s*@\s*@", repl, text, flags=re.IGNORECASE)


# Same token boundaries as _protect/_restore, but wrapped in a capturing
# group so re.split() keeps the matched tokens in its output, interleaved
# with the text between them.
_SPLIT_PATTERN = re.compile(f"({TOKEN_PATTERN.pattern})")


def split_segments(text):
    """
    Splits text into an ordered list of ('token', literal) / ('text', content)
    pieces at TOKEN_PATTERN boundaries (color codes, %1$s-style
    placeholders, {key.path} cross-references, __NL__ newline markers, PUA
    glyphs).

    Unlike _protect(), this does NOT substitute tokens with an opaque
    marker that then travels alongside real text -- it separates them out
    entirely. Callers should send ONLY the 'text' pieces to a translation
    service and pass 'token' pieces through completely untouched, so a
    translator never sees anything but genuine human-readable language
    (no placeholder-shaped noise mixed in that could get mistranslated or
    read as spam/repetition).

    Empty text pieces (two tokens with nothing between them) are omitted
    entirely, since join_segments()/straight concatenation reconstructs
    correctly either way.
    """
    raw = _SPLIT_PATTERN.split(text)
    parts = []
    for i, chunk in enumerate(raw):
        if i % 2 == 1:
            parts.append(("token", chunk))
        elif chunk:
            parts.append(("text", chunk))
    return parts


def join_segments(parts):
    """Inverse of split_segments() when given (kind, literal_text) pairs."""
    return "".join(content for _, content in parts)


def tokens_only_diff(old_text, new_text):
    """
    Compares an old and new base value and checks whether the *only*
    difference between them lives inside protected tokens (%1$s-style
    placeholders, section-sign color codes, PUA glyphs, etc) -- i.e. every
    bit of actual translatable text is byte-for-byte identical, only the
    token(s) themselves changed (a swapped placeholder index, a different
    color code, and so on).

    Returns the new token list (in order) if that's the case, so the caller
    can splice it into an already-translated string instead of retranslating.
    Returns None if there's any other change (meaning a real retranslation
    is needed), including the case where nothing changed at all.
    """
    old_skeleton, old_tokens = _protect(old_text)
    new_skeleton, new_tokens = _protect(new_text)
    if old_skeleton != new_skeleton:
        return None
    if old_tokens == new_tokens:
        return None
    return new_tokens


def apply_token_patch(translated_text, new_tokens):
    """
    Re-applies an updated token list onto an already-translated string
    without calling Google Translate. Only safe when the translated string
    contains the same number of protected tokens as the new base value --
    otherwise we can't line them up positionally, so the caller should fall
    back to a full retranslation. Returns None in that mismatch case.
    """
    skeleton, current_tokens = _protect(translated_text)
    if len(current_tokens) != len(new_tokens):
        return None
    return _restore(skeleton, new_tokens)


_KEY_REF_RE = re.compile(r"\{([^{}]+)\}")


def resolve_key_references(values, max_depth=10):
    """
    Resolves every '{other.key}' cross-reference in `values` (a dict of
    key -> value for ONE .lang file) into that other key's own value,
    within this same file/language -- so the final .lang holds real
    resolved text instead of a raw reference marker for the game to look
    up at runtime.

    A reference can itself contain another reference (resolved
    recursively, up to max_depth), is memoized so shared references are
    only resolved once, and is left as the literal '{other.key}' text
    (never guessed at or dropped) whenever it can't be resolved cleanly:
    the referenced key doesn't exist in this file, or resolving it would
    require re-entering a key already being resolved along the same
    chain (a cycle).

    Returns a new dict; `values` itself is not mutated.
    """
    resolved_cache = {}

    def resolve_value(key, depth, stack):
        if key in resolved_cache:
            return resolved_cache[key]
        text = values.get(key)
        if text is None:
            return None  # referenced key doesn't exist in this file
        if key in stack or depth > max_depth:
            return text  # cycle, or chain too deep -- bail out, leave it raw
        if "{" not in text:
            resolved_cache[key] = text
            return text

        stack = stack | {key}

        def repl(m):
            ref_key = m.group(1)
            if ref_key == key:
                return m.group(0)  # self-reference -- never substitute
            sub = resolve_value(ref_key, depth + 1, stack)
            return sub if sub is not None else m.group(0)

        result = _KEY_REF_RE.sub(repl, text)
        resolved_cache[key] = result
        return result

    return {key: resolve_value(key, 0, frozenset()) for key in values}


BRITISH_SPELLINGS = {
    "color": "colour", "colors": "colours", "colored": "coloured",
    "coloring": "colouring", "colorful": "colourful", "discolor": "discolour",
    "discolored": "discoloured", "favorite": "favourite", "favorites": "favourites", 
    "favor": "favour", "favors": "favours", "favored": "favoured", "favoring": "favouring",
    "honor": "honour", "honors": "honours", "honored": "honoured",
    "honoring": "honouring", "honorable": "honourable", "humor": "humour", 
    "humors": "humours", "humored": "humoured", "humorous": "humourous",
    "flavor": "flavour", "flavors": "flavours", "flavored": "flavoured",
    "flavoring": "flavouring", "behavior": "behaviour", "behaviors": "behaviours",
    "behavioral": "behavioural", "neighbor": "neighbour", "neighbors": "neighbours",
    "neighborhood": "neighbourhood", "neighborhoods": "neighbourhoods",
    "labor": "labour", "labors": "labours", "labored": "laboured",
    "rumor": "rumour", "rumors": "rumours", "armor": "armour", "armors": "armours", 
    "armored": "armoured", "harbor": "harbour", "harbors": "harbours",
    "vapor": "vapour", "vapors": "vapours", "savior": "saviour", "saviors": "saviours",
    "organize": "organise", "organizes": "organises", "organized": "organised", 
    "organizing": "organising", "organization": "organisation", 
    "organizations": "organisations", "realize": "realise", "realizes": "realises", 
    "realized": "realised", "realizing": "realising", "recognize": "recognise", 
    "recognizes": "recognises", "recognized": "recognised", "recognizing": "recognising",
    "apologize": "apologise", "apologizes": "apologises", "apologized": "apologised", 
    "apologizing": "apologising", "customize": "customise", "customizes": "customises",
    "customized": "customised", "customizing": "customising", "customizable": "customisable",
    "analyze": "analyse", "analyzes": "analyses", "analyzed": "analysed",
    "analyzing": "analising", "catalog": "catalogue", "catalogs": "catalogues",
    "dialog": "dialogue", "dialogs": "dialogues", "theater": "theatre", 
    "theaters": "theatres", "center": "centre", "centers": "centres", 
    "centered": "centred", "centering": "centring", "fiber": "fibre", 
    "fibers": "fibres", "defense": "defence", "defenses": "defences",
    "offense": "offence", "offenses": "offences", "license": "licence", 
    "licenses": "licences", "gray": "grey", "grays": "greys", "grayed": "greyed",
    "grayscale": "greyscale", "canceled": "cancelled", "canceling": "cancelling",
    "traveled": "travelled", "traveling": "travelling", "traveler": "traveller", 
    "travelers": "travellers", "modeled": "modelled", "modeling": "modelling",
    "jewelry": "jewellery", "aluminum": "aluminium", "skeptic": "sceptic", 
    "skeptics": "sceptics", "skeptical": "sceptical", "mustache": "moustache", 
    "mustaches": "moustaches", "mold": "mould", "molds": "moulds", 
    "molded": "moulded", "molding": "moulding", "plow": "plough", "plows": "ploughs",
}

_WORD_PATTERN = re.compile(r"[A-Za-z]+")

def _match_case(original_word, replacement):
    if original_word.isupper():
        return replacement.upper()
    if original_word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement

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
