def _slow_delay(level):
    """Backoff delay for a given slow level (1-indexed), doubling each
    level and capped so a bad run doesn't stall for absurd lengths of
    time. 1s, 2s, 4s, ... capped at 60s."""
    return min(60.0, 2 ** (level - 1))
