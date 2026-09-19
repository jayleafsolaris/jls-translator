import sys


def _report_applying(done, total):
    """
    Prints 'Applying Cross-References & Tokens… NN%' in place during
    --apply (see common/text_protect.py's resolve_key_references() and
    tokens_only_diff()/apply_token_patch(), and functions/cmd_apply.py) --
    a percentage rather than a fraction, since this pass is quick
    per-language and a raw fraction would barely move.

    `done` is expected to be the eased/smoothed value from a SmoothProgress
    instance, not the raw per-language index directly -- so the percentage
    climbs smoothly between languages instead of jumping straight from one
    language's fraction to the next.
    """
    pct = int(done / total * 100) if total else 100
    sys.stdout.write(f"\rApplying Cross-References & Tokens… {pct}%".ljust(60))
    sys.stdout.flush()
