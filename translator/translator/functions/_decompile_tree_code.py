import os
from ..common.code_obfuscate import is_compiled_code, decompile_code_text


def _decompile_tree_code(root, key):
    """
    Walks every .py file under `root` and, if it looks compiled (see
    common/code_obfuscate.py's is_compiled_code()), decompiles it in
    place using `key`. Returns the list of paths (relative to `root`)
    that were compiled but couldn't be decompiled -- missing/wrong key,
    or corrupted content. An empty list means everything under root is
    now plain, runnable Python.

    Never raises on a bad individual file -- it's reported back in the
    returned list instead, so the caller (--upgrade) can decide what a
    partial failure means for it, rather than this helper deciding to
    abort a walk the caller might still want to finish.
    """
    failed = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            try:
                text = open(path, "r", encoding="utf-8").read()
            except UnicodeDecodeError:
                continue  # not text we can even look at -- leave it alone
            if not is_compiled_code(text):
                continue
            rel = os.path.relpath(path, root)
            if key is None:
                failed.append(rel)
                continue
            try:
                original = decompile_code_text(text, key)
            except ValueError:
                failed.append(rel)
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(original)
    return failed
