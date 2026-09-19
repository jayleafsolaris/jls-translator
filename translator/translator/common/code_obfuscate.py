"""
Shared helpers for compiling/decompiling the tool's OWN .py source on the
way to and from GitHub (see functions/cmd_push.py, cmd_pull.py,
cmd_upgrade.py) -- the same lightweight, fully-reversible XOR+base64
obfuscation as common/obfuscate.py uses for `base`, keyed by its own
constant embedded directly in cli.py (see cli.py's own comment) rather than
base's fresh-random-every-run key, so it never collides with compiling
base -- the two can be in either state independently.

This is obfuscation, not encryption -- it exists so a public clone/browse
of the repo doesn't show plainly-readable source at a glance, not to
protect it against anyone willing to read this source (or cli.py, which
carries the key in the clear on purpose -- see cli.py). Any machine that
has a copy of cli.py -- which is to say, any machine that can run this
tool at all -- can freely --pull/--upgrade and get real, working Python
back, without any separate key-caching step.
"""
from .state import _CODE_COMPILE_KEY_MARKER
from ..functions._code_marker_line import _code_marker_line
from ..functions.compile_code_text import compile_code_text
from ..functions.decompile_code_text import decompile_code_text
from ..functions.is_compiled_code import is_compiled_code
