def _ask_continue(code):
    while True:
        answer = input(f"\nFinished {code}. Continue to next? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")
