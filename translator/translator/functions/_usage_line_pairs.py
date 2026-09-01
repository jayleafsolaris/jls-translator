from ._clock import _clock
from ._relative import _relative


def _usage_line_pairs(report, now):
    """(label, value) pairs for whichever usage lines currently apply --
    shared between the one-shot print and the --live redraw so the two
    can't drift out of sync with each other. Reset/cooldown lines are
    computed fresh from `now` rather than the precomputed *_reset_str
    fields on `report`, since --live needs those to actually count down
    tick to tick rather than being frozen at whenever the report was
    fetched."""
    pairs = [
        ("Daily Usage", f"{report['day_pct']:.0f}%"),
        ("Hourly Usage", f"{report['hour_pct']:.0f}%"),
    ]
    # If nothing's currently counted in a window, its "reset" is just
    # `now` (see _next_reset_epoch) -- there's no pending reset to show,
    # so skip the line rather than printing a reset time that's already
    # passed.
    if report["day_reset_epoch"] > now:
        pairs.append(("Daily Reset", f"{_clock(report['day_reset_epoch'])} (in {_relative(report['day_reset_epoch'])})"))
    if report["hour_reset_epoch"] > now:
        pairs.append(("Hourly Reset", f"{_clock(report['hour_reset_epoch'])} (in {_relative(report['hour_reset_epoch'])})"))
    if report["cooldown_active"]:
        pairs.append(("Manual Cooldown",
                       f"Expires at {_clock(report['cooldown_until_epoch'])} (in {_relative(report['cooldown_until_epoch'])})"))
    return pairs
