import re
from ..common.state import PACKAGE_DIR


def _find_pyproject_version(max_levels_up=6):
    """
    Walks upward from this script's own directory looking for a
    pyproject.toml, since in a typical package layout it lives at the repo
    root -- one or more directories above the actual module file (e.g.
    repo/pyproject.toml vs repo/src/roe_translator/translate.py) -- not
    necessarily right next to the script itself.

    Reads the version out of either a PEP 621 `[project]` table or a
    Poetry-style `[tool.poetry]` table, whichever is present. Returns None
    if no pyproject.toml with a parseable version is found within
    max_levels_up directories.
    """
    directory = PACKAGE_DIR
    for _ in range(max_levels_up + 1):
        candidate = directory / "pyproject.toml"
        if candidate.exists():
            try:
                text = candidate.read_text(encoding="utf-8")
            except Exception:
                text = None
            if text:
                # Prefer a version line that appears under [project] or
                # [tool.poetry] specifically, since a pyproject.toml can
                # contain other "version = ..." lines (build-system
                # requirements, tool configs, etc) that aren't the
                # package's own version.
                for table in (r"\[project\]", r"\[tool\.poetry\]"):
                    section = re.search(
                        rf'{table}(.*?)(?=\n\[|\Z)', text, re.DOTALL
                    )
                    if section:
                        match = re.search(
                            r'(?m)^\s*version\s*=\s*"([^"]+)"', section.group(1)
                        )
                        if match:
                            return match.group(1)
                # Fall back to the first bare version line anywhere in the
                # file if neither table matched (unusual pyproject.toml
                # layout) -- better than nothing.
                match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
                if match:
                    return match.group(1)
            # A pyproject.toml exists here but had no usable version --
            # stop climbing rather than risk picking up an unrelated one
            # further up the tree.
            return None
        if directory.parent == directory:
            break
        directory = directory.parent
    return None
