"""--usage: show current translation usage against the hourly/daily caps,
and --cooldown: manually force a cooldown on top of them."""
import sys
import time
from ..common.ratelimit import status_report, set_manual_cooldown
from ..functions._clock import _clock
from ..functions._cmd_usage_live import _cmd_usage_live
from ..functions._relative import _relative
from ..functions._usage_line_pairs import _usage_line_pairs
from ..functions.cmd_usage import cmd_usage
