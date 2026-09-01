from ..common.state import TOKEN_PATTERN


def _protect(text):
    tokens = []
    def repl(m):
        tokens.append(m.group(0))
        return f"@@PH{len(tokens) - 1}@@"
    return TOKEN_PATTERN.sub(repl, text), tokens
