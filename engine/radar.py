"""Future Skills Radar: chart data and plain sentences (pure functions, no Streamlit).

The radar plots every skill whose status is "ok" or "low_volume":
  x = share of job posts that mention the skill now (log scale),
  y = change in that share, last 12 months against the 12 months before.
Only a skill whose Welch trend label is Rising or Falling gets a coloured mark. Every other
skill is grey, so the chart never claims a change the test did not find.

All numbers come from data/skill_scores.json (and backtest.json for the hit rate). Nothing
here is estimated. See docs/pathway.md for how the journey uses it.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Iterable, Mapping, Sequence

PLOT_STATUSES = ("ok", "low_volume")
RISING, FALLING = "Rising", "Falling"
TESTED_LABELS = (RISING, FALLING)
GREY_GROUP = "No clear change"
# The three AI stances in the order of the colour slots, then the grey group.
STANCES = ("AI-complement", "AI-substitutable", "neutral")
COLOUR_GROUPS = STANCES + (GREY_GROUP,)
QUADRANT_NAMES = {
    (True, True): "Common, share up",
    (True, False): "Common, share down",
    (False, True): "Small, share up",
    (False, False): "Small, share down",
}
# How a plotted skill is drawn: coloured and filled, coloured and hollow (stance contested), grey.
MARK_FILLED, MARK_HOLLOW, MARK_GREY = "filled", "hollow", "grey"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value  # not NaN


def share_change(skill: Mapping[str, Any]) -> float | None:
    """(share last 12 months / share prior 12 months) - 1, or None when it cannot be computed."""
    m12, p12 = skill.get("mentions_last12"), skill.get("posts_last12")
    mprev, pprev = skill.get("mentions_prev12"), skill.get("posts_prev12")
    if not all(_is_number(v) for v in (m12, p12, mprev, pprev)):
        return None
    if p12 <= 0 or pprev <= 0 or mprev <= 0:
        return None
    return (m12 / p12) / (mprev / pprev) - 1.0


def _mark(label: str | None, contested: bool) -> str:
    if label not in TESTED_LABELS:
        return MARK_GREY
    return MARK_HOLLOW if contested else MARK_FILLED


def radar_points(skills: Iterable[Mapping[str, Any]], my_skills: Iterable[str] = (),
                 contested: Iterable[str] = ()) -> dict[str, Any]:
    """Chart rows for the radar.

    Returns {"points": [...], "share_cut": float | None, "skipped": [names]}.
    `share_cut` is the median share of the plotted skills: it splits Strong from Small.
    A skill is skipped when it has no usable status, share or 12-month counts.
    """
    mine, contested_set = set(my_skills), set(contested)
    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for s in skills:
        name = s.get("skill")
        if s.get("status") not in PLOT_STATUSES:
            continue
        share, change = s.get("demand_share_latest"), share_change(s)
        if not _is_number(share) or share <= 0 or change is None:
            skipped.append(name)
            continue
        label = s.get("trend_label")
        is_contested = name in contested_set
        mark = _mark(label, is_contested)
        stance = s.get("stance")
        rows.append({
            "skill": name,
            "share": float(share),
            "change": float(change),
            "trend_label": label or "No label",
            "trend_p": s.get("trend_p") if _is_number(s.get("trend_p")) else None,
            "stance": stance or "n/a",
            "contested": is_contested,
            "mine": name in mine,
            "status": s.get("status"),
            "mark": mark,
            "group": (stance if stance in STANCES else "neutral") if mark != MARK_GREY else GREY_GROUP,
        })
    cut = median(r["share"] for r in rows) if rows else None
    for r in rows:
        r["quadrant"] = QUADRANT_NAMES[(r["share"] >= cut, r["change"] >= 0)]
    return {"points": rows, "share_cut": cut, "skipped": skipped}


def _names(points: Sequence[Mapping[str, Any]]) -> str:
    return ", ".join(p["skill"] for p in points)


def user_counts(points: Sequence[Mapping[str, Any]], share_cut: float | None) -> dict[str, Any]:
    """Where the user's skills sit: rising and falling by the test, the rest as steady (strong or small)."""
    mine = [p for p in points if p["mine"]]
    rising = [p for p in mine if p["trend_label"] == RISING]
    falling = [p for p in mine if p["trend_label"] == FALLING]
    steady = [p for p in mine if p["trend_label"] not in TESTED_LABELS]
    strong = [p for p in steady if share_cut is not None and p["share"] >= share_cut]
    small = [p for p in steady if p not in strong]
    return {"n": len(mine), "rising": rising, "falling": falling, "strong_steady": strong,
            "small_steady": small}


def _movers(points: Sequence[Mapping[str, Any]], label: str) -> str:
    """'RAG (+86%), PostgreSQL (+28%)' for the skills with `label`, biggest change first; 'none' if empty."""
    hits = sorted((p for p in points if p["trend_label"] == label), key=lambda p: -abs(p["change"]))
    return ", ".join(f"{p['skill']} ({p['change']:+.0%})" for p in hits) or "none"


def summary_sentences(radar: Mapping[str, Any], my_skills: Iterable[str]) -> list[str]:
    """Three plain sentences built from the data: yours, the whole market, the tested movers."""
    points, cut = radar["points"], radar["share_cut"]
    c = user_counts(points, cut)
    off_chart = len(list(my_skills)) - c["n"]

    if c["n"] == 0:
        first = "Pick your skills in step 1 to see where they sit on the chart."
    else:
        parts = [f"{len(c['strong_steady'])} strong, no clear change"]
        if c["small_steady"]:
            parts.append(f"{len(c['small_steady'])} small, no clear change")
        parts.append(f"{len(c['rising'])} rising" + (f" ({_names(c['rising'])})" if c["rising"] else ""))
        parts.append(f"{len(c['falling'])} falling" + (f" ({_names(c['falling'])})" if c["falling"] else ""))
        first = "Your skills: " + ", ".join(parts) + "."
        if off_chart > 0:
            first += f" {off_chart} of your skills {'is' if off_chart == 1 else 'are'} too rare in posts to plot."

    n = len(points)
    rising = sum(p["trend_label"] == RISING for p in points)
    falling = sum(p["trend_label"] == FALLING for p in points)
    second = (f"Across all {n} skills on the chart: {rising} rising, {falling} falling and "
              f"{n - rising - falling} with no clear change over the last 12 months.")
    third = (f"Tested movers, with the change in their share of posts: rising, {_movers(points, RISING)}; "
             f"falling, {_movers(points, FALLING)}.")
    return [first, second, third]


def how_to_read(backtest: Mapping[str, Any] | None = None) -> str:
    """The caption under the chart. The backtest figure comes from backtest.json when it exists."""
    tl = (backtest or {}).get("trend_label_backtest") or {}
    rate = tl.get("trend_label_hit_rate")
    tested = (f" The labels are tested: in our backtest a Rising or Falling label pointed the right way "
              f"{rate:.0%} of the time (n = {tl.get('n')} labelled skill-origins)." if _is_number(rate) else "")
    return (
        "How to read it: further right means more job posts mention the skill (share of Hacker News 'Who is "
        "hiring?' posts, log scale). Higher means that share grew over the last 12 months against the 12 before. "
        "A filled colour mark means a statistical test found a change unlikely to be chance alone (Welch, p < 0.05; "
        "each skill is tested separately, so a few labels can be wrong). A hollow mark means "
        "the same, but the published AI-exposure indices disagree on its stance. Grey means no clear change: the true change may "
        "be zero, whatever the dot's height." + tested + " A black ring and a label mark your skills. "
        "The dashed lines split the chart at the median share and at no change.")
