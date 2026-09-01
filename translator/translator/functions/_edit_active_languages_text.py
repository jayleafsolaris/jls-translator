from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME


def _edit_active_languages_text(codes, active_set):
    selected = set(active_set)
    while True:
        print()
        for i, code in enumerate(codes, start=1):
            marker = "I" if code in selected else "O"
            name = LANGUAGE_NAMES.get(code, "")
            print(f"  {i:>2}. [{marker}] {code:<8} {name}")
        print("\n[I] = active (in)   [O] = inactive (out)")
        raw = input(
            "Enter number(s) to toggle (comma-separated), 'a' to toggle all, "
            "'done' to save, 'q' to cancel: "
        ).strip().lower()

        if raw in ("q", "quit", "cancel"):
            return None
        if raw in ("done", "d", ""):
            return selected
        if raw in ("a", "all"):
            selected = set() if len(selected) == len(codes) else set(codes)
            continue

        parts = [p.strip() for p in raw.split(",") if p.strip()]
        idxs = []
        ok = True
        for p in parts:
            if not p.isdigit() or not (1 <= int(p) <= len(codes)):
                print(f"'{p}' isn't a valid number 1-{len(codes)}.")
                ok = False
                break
            idxs.append(int(p))
        if not ok:
            continue

        for i in idxs:
            code = codes[i - 1]
            if code in selected:
                selected.discard(code)
            else:
                selected.add(code)
