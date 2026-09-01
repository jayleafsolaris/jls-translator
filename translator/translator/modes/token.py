"""--token: add or remove the GitHub personal access token used by --push/--pull."""
from ..common.github_api import get_token, set_token, remove_token
from ..functions._mask import _mask
from ..functions.cmd_remove_token import cmd_remove_token
from ..functions.cmd_set_token import cmd_set_token
from ..functions.cmd_show_token import cmd_show_token
