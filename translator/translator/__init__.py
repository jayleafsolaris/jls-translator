"""
jls-translator: keeps a set of Minecraft Bedrock .lang files in sync with
a single hand-edited `base` source file.

This package is split by operation mode:

    translator/
        common/     shared state, .lang I/O, translation, caching, progress
        modes/      one module per --create/--update/--add/--... command
        cli.py      argument parsing and the interactive prompts/dispatch

The dependency check below runs first, before any submodule tries to
`import requests` or `from deep_translator import GoogleTranslator` on its
own, so a missing dependency always produces this friendly message instead
of a raw traceback from whichever module happened to import it first.
"""

import sys

# ----------------------------------------------------------------------
# Dependency Check
# ----------------------------------------------------------------------
try:
    import requests
    from deep_translator import GoogleTranslator
except ImportError:
    print("\033[91m\nError: Missing required dependencies.\033[0m")
    print("This script requires 'deep_translator' and 'requests' to run.")
    print("Please install them by running:\n\n    pip install deep_translator requests\n")
    sys.exit(1)

from .cli import main

__all__ = ["main"]
