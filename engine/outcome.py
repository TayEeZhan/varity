"""Grade a past forecast against what happened, the same way the backtest does.

engine/backtest.py (evaluate_bands) checks the band against the SINGLE target month value
y = logit(smoothed_share(mentions, n_posts)) at month as_of + 12. The same rule is used here,
so the share of "inside" verdicts over many as-of months equals the band coverage in
data/backtest.json. A pooled 3-month share is a different quantity and is not used.

Only the Moderate band is calibrated (rolling conformal). The Fast band is an assumption
and is never graded.
"""
from __future__ import annotations

from engine.forecast import smoothed_share


def band_verdict(moderate: dict, mentions, n_posts) -> dict:
    """Place the target month's smoothed share against the Moderate band.

    `moderate` is forecast["moderate"] of a skill with status "ok" (keys low, high).
    Returns {"actual": share, "place": "below" | "inside" | "above", "inside": bool}.
    """
    actual = float(smoothed_share(mentions, n_posts))
    low, high = moderate["low"], moderate["high"]
    place = "below" if actual < low else "above" if actual > high else "inside"
    return {"actual": actual, "place": place, "inside": place == "inside"}
