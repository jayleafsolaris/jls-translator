"""
jls-translator: keeps a set of Minecraft Bedrock .lang files in sync with
a single hand-edited `base` source file.

This package is split by operation mode:

    translator/
        common/     shared state, .lang I/O, translation, caching, progress
        modes/      one module per --create/--update/--add/--... command
        cli.py      argument parsing and the interactive prompts/dispatch

Translation runs entirely locally via Argos Translate (offline MT models,
downloaded once per language pair and cached -- no per-run network calls,
no external rate limit to respect). `requests` is still needed separately
for --push/--pull/--upgrade (common/github_api.py) and the GitHub-based
update checker (common/netcheck.py).

The dependency check below runs first, before any submodule tries to
`import requests` or `import argostranslate` on its own, so a missing
dependency always produces this friendly message instead of a raw
traceback from whichever module happened to import it first.
"""

import sys

# ----------------------------------------------------------------------
# Dependency Check
# ----------------------------------------------------------------------
try:
    import requests
    import argostranslate.package
    import argostranslate.translate
except ImportError:
    print("\033[91m\nError: Missing required dependencies.\033[0m")
    print("This script requires 'argostranslate' and 'requests' to run.")
    print("Please install them by running:\n\n    pip install argostranslate requests\n")
    sys.exit(1)

from .cli import main

__all__ = ["main"]
