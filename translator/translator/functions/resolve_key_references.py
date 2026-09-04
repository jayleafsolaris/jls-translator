from ..common.text_protect import _KEY_REF_RE


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
