from ..common.state import DEFAULTS, LANGUAGES, LANGUAGE_NAMES, PACKAGE_DIR, CONFIG_DIR_VISIBLE_NAME, CONFIG_DIR_HIDDEN_NAME


def _edit_active_languages_curses(codes, active_set):
    import curses

    def _run(stdscr):
        curses.curs_set(0)
        idx = 0
        top = 0
        selected = set(active_set)
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            stdscr.addstr(0, 0, "Active languages", curses.A_BOLD)
            stdscr.addstr(1, 0, "SPACE toggle  A all/none  ENTER save  Q cancel"[:max(w - 1, 0)])
            visible = max(h - 4, 1)
            if idx < top:
                top = idx
            if idx >= top + visible:
                 top = idx - visible + 1
            for row, code in enumerate(codes[top:top + visible]):
                real_i = top + row
                mark = "[x]" if code in selected else "[ ]"
                name = LANGUAGE_NAMES.get(code, "")
                line = f"{mark} {code:<8} {name}"
                attr = curses.A_REVERSE if real_i == idx else curses.A_NORMAL
                try:
                    stdscr.addstr(row + 3, 2, line[:max(w - 4, 0)], attr)
                except curses.error:
                    pass
            stdscr.refresh()
            key = stdscr.getch()
            if key in (curses.KEY_UP, ord('k'), ord('K')):
                idx = max(0, idx - 1)
            elif key in (curses.KEY_DOWN, ord('j'), ord('J')):
                idx = min(len(codes) - 1, idx + 1)
            elif key == ord(' '):
                if codes[idx] in selected:
                    selected.discard(codes[idx])
                else:
                    selected.add(codes[idx])
            elif key in (ord('a'), ord('A')):
                selected = set() if len(selected) == len(codes) else set(codes)
            elif key in (curses.KEY_ENTER, 10, 13):
                return selected
            elif key in (ord('q'), ord('Q'), 27):
                return None

    return curses.wrapper(_run)
