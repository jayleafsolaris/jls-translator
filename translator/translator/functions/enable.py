from ..common.debug_log import _enabled


def enable():
    """Called from cli.py when --debug is combined with another mode."""
    global _enabled
    _enabled = True
