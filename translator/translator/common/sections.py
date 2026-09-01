"""
Shared helpers for --split/--merge: turning `base` into a nested folder
hierarchy that mirrors EVERY heading depth ('##', '###', '####', ...),
and rebuilding `base` from that hierarchy again.

Any line matching '#'*2-or-more followed by whitespace is a heading, and
its hash count is its depth. Each heading becomes a folder named after
its (sanitized) text, nested inside its parent heading's folder. A
heading's own content -- the lines that appear directly under it, before
its first child heading -- is written as that folder's `keys.txt`. A
heading with no content of its own (just child headings) gets no
keys.txt, only subfolders.

Example, given:

    ## UI
    ### PACK DETAILS
    ui.roe:pack.name

--split produces (base/ being the top-level replacement for the base
file itself):

    base/UI/PACK DETAILS/keys.txt      <- contains "ui.roe:pack.name"

`base` must open with a single '##' heading (exactly two hashes) --
that's the root wrapper for everything under it (e.g. an addon's own
name). Any FURTHER '##' heading anywhere else in the document is not
special in any way -- it's just another heading, nested wherever it
appears, same as any '###'/'####'/etc. This is what lets someone fold a
second addon's lang into `base` just by dropping in another
'## SomeAddonName' heading somewhere.

The one real exception is the --update run-count marker (see state.py's
_UPDATE_COUNT_MARKER) -- a "##"-prefixed line with no space after the
hashes, e.g. `##24175e243bcdb082a4fee9e61=13`, conventionally sitting at
the very bottom of base. It never matches the heading pattern (no
whitespace after '##'), and on top of that it's explicitly recognized
and pulled out of the tree entirely here -- it's never attributed to any
section, never written into any keys.txt, and gets reappended verbatim
at the very end of the file on --merge.

Blank lines are also never written into a keys.txt -- each heading's
content is split into its actual (non-blank) lines for keys.txt, and a
separate positional record of exactly which lines were blank (and their
raw text). --merge splices those blank lines back into their original
positions, so the reassembled `base` is byte-for-byte identical to what
was split.
"""
import json
import re
from .state import DEFAULTS, PACKAGE_DIR, _UPDATE_COUNT_MARKER
_HEADER_RE = re.compile(r'^(#{2,})[ \t]+(\S.*)$')
_UNSAFE_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
_UPDATE_MARKER_PREFIX = f"##{_UPDATE_COUNT_MARKER}="
KEYS_FILENAME = "keys.txt"
class Node:
    """One heading in the tree. The synthetic root (level=1, name=None) is
    never itself written out -- only its descendants are."""

    __slots__ = ("level", "name", "folder", "content_raw", "key_text", "blanks", "children")

    def __init__(self, level, name, folder):
        self.level = level
        self.name = name
        self.folder = folder
        self.content_raw = []   # raw lines under this heading, blanks/keys not yet separated
        self.key_text = ""      # filled in by _finalize(): the eventual keys.txt content
        self.blanks = []        # filled in by _finalize(): [{"pos": i, "text": raw_line}, ...]
        self.children = []      # list of Node, in source order
from ..functions._finalize import _finalize
from ..functions._node_to_dict import _node_to_dict
from ..functions._reconstruct_content import _reconstruct_content
from ..functions._section_data_path import _section_data_path
from ..functions.find_duplicate_siblings import find_duplicate_siblings
from ..functions.load_section_data import load_section_data
from ..functions.parse_tree import parse_tree
from ..functions.preview_paths import preview_paths
from ..functions.render_tree import render_tree
from ..functions.sanitize_name import sanitize_name
from ..functions.save_section_data import save_section_data
from ..functions.write_tree import write_tree
