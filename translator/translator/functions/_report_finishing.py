import sys


def _report_finishing(done, total):
    """
    Prints 'Finishing Translations… NN%' in place during --update's
    post-translation key-reference resolution phase (see
    common/text_protect.py's resolve_key_references() and modes/update.py)
    -- a percentage rather than a fraction, since this phase is quick
    per-language and a raw fraction would barely move.

    `done` is expected to be the eased/smoothed value coming from a
    SmoothProgress instance (the same easing used for the main translation
    bars in this module), not the raw per-language index directly -- so
    the percentage climbs smoothly between languages instead of jumping
    straight from one language's fraction to the next.
    """
    pct = int(done / total * 100) if total else 100
    sys.stdout.write(f"\rFinishing Translations… {pct}%".ljust(60))
    sys.stdout.flush()
