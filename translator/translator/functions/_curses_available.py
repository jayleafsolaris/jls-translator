import sys


def _curses_available():
    try:
        import curses
    except ImportError:
        return False
    return sys.stdout.isatty() and sys.stdin.isatty()
