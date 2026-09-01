import os


def _find_package_source(extracted_root):
    """
    GitHub wraps the whole repo in a single top-level folder (e.g.
    'translator-main/'). In this repo that wrapper folder is NOT the package
    itself -- the real package (cli.py, common/, modes/) lives one level
    deeper, at 'translator-main/translator/'. Walk the extracted tree and
    return the directory that actually contains cli.py, rather than assuming
    the zip's outer wrapper folder is it. Falls back to extracted_root if no
    such directory is found, so an unexpected layout doesn't hard-crash.
    """
    for dirpath, dirnames, filenames in os.walk(extracted_root):
        if "cli.py" in filenames:
            return dirpath
    return extracted_root
