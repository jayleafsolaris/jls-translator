import re


def _restore(text, tokens):
    def repl(m):
        idx = int(m.group(1))
        return tokens[idx] if idx < len(tokens) else m.group(0)
    return re.sub(r"@\s*@\s*PH\s*(\d+)\s*@\s*@", repl, text, flags=re.IGNORECASE)
