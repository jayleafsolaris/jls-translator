from ..cli import _MODES, _MODE_FLAG_NAME


def prompt_for_mode():
    print("No mode specified. What would you like to do?\n")
    for i, (key, desc) in enumerate(_MODES, start=1):
        flag = _MODE_FLAG_NAME.get(key, f"--{key}")
        print(f"  {i}. {flag:<12} {desc}")

    while True:
        raw = input(f"\nChoose 1-{len(_MODES)}: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= idx <= len(_MODES):
            return _MODES[idx - 1][0]
        print(f"Please enter a number between 1 and {len(_MODES)}.")
