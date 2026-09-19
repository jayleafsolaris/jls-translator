from . import reserve as reserve_mod
import contextlib


@contextlib.contextmanager
def _quiet_warnings(sink):
    """Temporarily reroutes the warn_red() call inside reserve()'s
    self-resolving hourly-cap pause into `sink` (a list) instead of the
    terminal, for the duration of one retryable attempt -- so that
    warning doesn't get announced while --update is still quietly
    waiting out the hourly window and retrying on its own.

    NOTE: this used to patch common/translate.py's and
    common/ratelimit.py's own warn_red attributes, back when the actual
    warn_red() calls lived inline in those two files. The one-function-
    per-file extraction (see INDEX.md) moved every real call site out
    into its own module under functions/, each with its OWN independent
    `from ..common.config_store import warn_red` import -- a fresh local
    binding, not a live reference back into common/translate.py or
    common/ratelimit.py. Patching THOSE modules' now-orphaned warn_red
    attribute silently did nothing, and every warning meant to stay
    quiet during a retry (this hourly-pause one included) leaked
    straight to the terminal instead, corrupting --update's fixed-line
    progress redraw. This patches the module that actually still calls
    warn_red mid-retry.

    Deliberately does NOT touch sys.stdout itself: translate_many()'s
    progress_cb fires through the same stdout via the live progress
    renderer, and swallowing that too (an earlier version of this did,
    via redirect_stdout) breaks the progress display for the entire
    attempt, success or not.

    Does NOT cover _handle_rate_limit_stop's or
    _translate_segments_deferred's warn_red calls -- both of those only
    fire at a genuinely terminal give-up point (right before a deliberate
    sys.exit()/raise that ends the run for real), so hiding them would
    just delay the real explanation rather than mask a transient retry.
    Always restores the real warn_red on the way out, success or
    failure."""
    real_reserve_warn = reserve_mod.warn_red

    def _capture(message):
        sink.append(message)

    reserve_mod.warn_red = _capture
    try:
        yield
    finally:
        reserve_mod.warn_red = real_reserve_warn
