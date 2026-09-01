from ..common import ratelimit as ratelimit_mod
from ..common import translate as translate_mod
import contextlib


@contextlib.contextmanager
def _quiet_warnings(sink):
    """Temporarily reroutes the warn_red() calls that live inside
    translate.py/ratelimit.py into `sink` (a list) instead of the
    terminal, for the duration of one retryable attempt -- so an
    outage/rate-limit warning that fires mid-attempt doesn't get
    announced while --update is still quietly retrying it.

    Deliberately does NOT touch sys.stdout itself: translate_many()'s
    progress_cb fires through the same stdout via the live progress
    renderer, and swallowing that too (an earlier version of this did,
    via redirect_stdout) breaks the progress display for the entire
    attempt, success or not. Only the two known warn_red call sites are
    redirected, leaving everything else untouched. Always restores the
    real warn_red on the way out, success or failure."""
    real_translate_warn = translate_mod.warn_red
    real_ratelimit_warn = ratelimit_mod.warn_red

    def _capture(message):
        sink.append(message)

    translate_mod.warn_red = _capture
    ratelimit_mod.warn_red = _capture
    try:
        yield
    finally:
        translate_mod.warn_red = real_translate_warn
        ratelimit_mod.warn_red = real_ratelimit_warn
