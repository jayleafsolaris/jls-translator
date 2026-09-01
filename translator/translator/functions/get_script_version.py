try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover -- Python < 3.8 doesn't ship this
    importlib_metadata = None
from ..common.state import PACKAGE_NAME, _FALLBACK_VERSION
from ._find_pyproject_version import _find_pyproject_version


def get_script_version():
    """
    Reads the running script's version from installed package metadata
    (populated by pip from pyproject.toml's [project] version at install
    time), so there's a single source of truth instead of a hardcoded
    string here that can drift out of sync with pyproject.toml.

    If the package isn't pip-installed (e.g. running the .py file directly,
    such as under a-Shell), importlib metadata has nothing to look up --
    in that case, fall back to reading the version straight out of a
    pyproject.toml sitting next to this script, so --version still reports
    the real version instead of the dev placeholder. Only if that also
    can't be found does it fall back to the placeholder.
    """
    if importlib_metadata is not None:
        try:
            return importlib_metadata.version(PACKAGE_NAME)
        except importlib_metadata.PackageNotFoundError:
            pass
        except Exception:
            pass

    found = _find_pyproject_version()
    if found:
        return found

    return _FALLBACK_VERSION
