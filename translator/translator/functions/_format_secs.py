def _format_secs(secs):
    secs = max(0, int(secs))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)

    units = [("d", d), ("h", h), ("m", m), ("s", s)]
    nonzero = [(label, val) for label, val in units if val]

    if not nonzero:
        return "0s"
    return " ".join(f"{val}{label}" for label, val in nonzero)
