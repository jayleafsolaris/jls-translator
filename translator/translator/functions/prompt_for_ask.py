def prompt_for_ask():
    raw = input("Ask for confirmation after each item finishes? [y/N]: ").strip().lower()
    return raw in ("y", "yes")
