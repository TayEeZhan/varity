"""Verity: Streamlit front end for skill forecasts.

Reads data/skill_scores.json (engine output) when it exists, otherwise the sample file
data/fixtures/skill_scores.json. Every number on screen comes from a file in the data folder
(skill_scores.json, demand_monthly.csv, ai_context_monthly.csv, backtest.json, taxonomy.json,
SOURCES.md). No statistic is written in this file. No LLM is used.

Five tabs: Roles (role match for a chosen or edited skill set), Pathway (ordered plan and daily
to-do list for the chosen target role, engine.pathway), Skills (table), Skill detail (chart, text,
sources), Method (backtest).
Sidebar: scenario, "As of" month (reruns the engine with data up to that month, nothing is
written), and "Refresh live data" (engine.refresh.refresh).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine import live  # noqa: E402  (shared snapshot store; needs BASE_DIR on sys.path)

st.set_page_config(page_title="Verity", layout="wide")

DEFAULT_DATA_DIR = BASE_DIR / "data"
SCORES_NAME = "skill_scores.json"
FIXTURE_PATH = DEFAULT_DATA_DIR / "fixtures" / SCORES_NAME

NA = "n/a"
HORIZON_MONTHS = 12  # months between as_of and the forecast target
SCENARIO_KEYS = ["moderate", "fast"]
FIXTURE_BANNER = "Prototype: showing sample data, not real forecasts."
PARTIAL_NOTE = "The latest month's thread is still open; its numbers can change."
NO_LABEL = "No label"
BUSY_NOTE = "A refresh is already running; try again in a few seconds."
# Plain-words description of each production model (engine.forecast PRODUCTION_MODELS).
MODEL_WORDS = {"naive": "last month's value", "naive3": "mean of last 3 months"}

# Chart colours: slots 1 and 2 of the validated categorical palette (dataviz skill,
# references/palette.md), light and dark. Grey is neutral ink for the thin monthly line.
SERIES_BLUE = {"light": "#2a78d6", "dark": "#3987e5"}
SERIES_ORANGE = {"light": "#eb6834", "dark": "#d95926"}
SERIES_AQUA = {"light": "#1baf7a", "dark": "#199e70"}
MUTED_GREY = "#8b8a84"

# Role match (engine.roles). Three synthetic example profiles until the CV extractor lands.
# The skill names must be taxonomy names. They are examples, not real people.
PERSONAS = {
    "Aina, junior Python dev (synthetic)": ["Python", "SQL", "PostgreSQL", "Docker", "AWS"],
    "Ben, frontend dev (synthetic)": ["JavaScript / TypeScript", "TypeScript", "React", "Node.js"],
    "Chloe, data analyst (synthetic)": ["SQL", "Python", "Snowflake", "dbt"],
}
ROLE_FILES = ("roles.json", "role_profiles.json", "role_demand_monthly.csv", "exposure.csv")
NO_TARGET_PROMPT = "Choose a target role in the Roles tab first"
TREND_BADGE = {"Rising": ":green-badge[Rising]", "Falling": ":red-badge[Falling]",
               "No clear change": ":gray-badge[No clear change]"}


# --------------------------------------------------------------------------------------
# Loading (cached by path and modification time)
# --------------------------------------------------------------------------------------

@st.cache_data
def load_scores(path: str, mtime: float) -> dict:
    """Read the scores file at `path`.

    `mtime` is not used in the body. It is an argument so that the cache key
    changes when the file is rewritten, which makes the cache refresh itself.
    """
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data
def load_json(path: str, mtime: float):
    """Read any JSON file. `mtime` only keys the cache."""
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data
def load_csv(path: str, mtime: float) -> pd.DataFrame:
    """Read any CSV file. `mtime` only keys the cache."""
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_text(path: str, mtime: float) -> str:
    """Read any text file. `mtime` only keys the cache."""
    return Path(path).read_text(encoding="utf-8")


def read_json(path: Path):
    """Cached JSON from `path`, or None when the file does not exist."""
    return load_json(str(path), path.stat().st_mtime) if path.exists() else None


def read_csv(path: Path) -> pd.DataFrame | None:
    """Cached CSV from `path`, or None when the file does not exist."""
    return load_csv(str(path), path.stat().st_mtime) if path.exists() else None


@st.cache_data(show_spinner=False)
def scores_as_of(data_dir: str, as_of: str, demand_mtime: float) -> dict:
    """Engine output with data up to `as_of`. Cached by as_of. Writes no file.

    `demand_mtime` only keys the cache, so a refresh that changes the demand table
    makes the cached as-of views stale and they are computed again.
    """
    from engine.scores import build_scores

    return build_scores(as_of=as_of, data_dir=data_dir)


@st.cache_data(show_spinner=False)
def role_trends_as_of(demand_path: str, roles_path: str, as_of: str, mtime: float) -> dict:
    """Role trend labels cut at `as_of` from role_demand_monthly.csv (never later months). Writes no file."""
    import engine.roles as roles_mod

    return roles_mod.build_role_trends(roles_mod.read_demand_rows(demand_path), roles_mod.load_roles(roles_path),
                                       as_of=as_of)


def default_scores_path(data_dir: Path) -> Path:
    """Engine output in `data_dir` if it exists, otherwise the sample fixture."""
    candidate = data_dir / SCORES_NAME
    return candidate if candidate.exists() else FIXTURE_PATH


# --------------------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------------------

def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def pct(value, digits: int = 1) -> str:
    """Format a share (0 to 1) as a percent."""
    return f"{value:.{digits}%}" if _is_number(value) else NA


def pp_plain(value, unit: bool = True) -> str:
    """Percentage points with 1 decimal, or n/a. Never 0 for a missing value."""
    return (f"{value:.1f}" + (" pp" if unit else "")) if _is_number(value) else NA


def signed_pp(value) -> str:
    """Format percentage points with a sign."""
    return f"{value:+.1f} pp" if _is_number(value) else NA


def get_forecast(skill: dict, scenario: str) -> dict:
    """Return the forecast block for one scenario, or {} if it is missing."""
    forecast = skill.get("forecast")
    if not isinstance(forecast, dict):
        return {}
    fc = forecast.get(scenario)
    return fc if isinstance(fc, dict) else {}


def forecast_text(skill: dict, scenario: str) -> str:
    """'value (low to high)' as percents, or 'n/a' when the status is not ok or no value exists."""
    status = skill.get("status")
    fc = get_forecast(skill, scenario)
    if (status is not None and status != "ok") or not _is_number(fc.get("value_12m")):
        return NA
    return f"{pct(fc['value_12m'])} ({pct(fc.get('low'))} to {pct(fc.get('high'))})"


def share_text(skill: dict) -> str:
    """'share (mentions/posts posts)'."""
    base = pct(skill.get("demand_share_latest"))
    m, n = skill.get("mentions_last3"), skill.get("posts_last3")
    return f"{base} ({m}/{n} posts)" if _is_number(m) and _is_number(n) else base


def trend_text(skill: dict) -> str:
    """'Rising (309 vs 273 mentions)'. The counts are mentions in the last 12 months vs the 12 before."""
    label = skill.get("trend_label")
    m12, mprev = skill.get("mentions_last12"), skill.get("mentions_prev12")
    counts = f" ({m12} vs {mprev} mentions)" if _is_number(m12) and _is_number(mprev) else ""
    if label is None:
        return NO_LABEL + counts if counts else NA
    return f"{label}{counts}"


def sdg_text(skill: dict) -> str:
    sdg = skill.get("sdg") or []
    return ", ".join(str(tag) for tag in sdg) if sdg else NA


def month_add(month: str, delta: int) -> str:
    """'2023-12' + 12 -> '2024-12'."""
    return str(pd.Period(month, freq="M") + delta)


def is_dark_theme() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:  # not available in every runtime
        return False


# --------------------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------------------

def line_chart(long: pd.DataFrame, forecast: pd.DataFrame | None, domain: list[str],
               colors: list[str], y_title: str, outcome: pd.DataFrame | None = None) -> alt.Chart:
    """Thin monthly line, thicker smoothed line, an optional forecast point with a band and an
    optional outcome marker (what happened).

    `long` has columns date, series, value. `forecast` has date, series, value, low, high.
    `outcome` has date, series, value. `domain` lists the series names in the order of `colors`:
    monthly, smoothed, then the forecast (if given), then the outcome (if given).
    A legend names every series, so colour is never the only cue.
    """
    scale = alt.Scale(domain=domain, range=colors)
    color = alt.Color("series:N", scale=scale, legend=alt.Legend(title=None, orient="top"))
    x = alt.X("date:T", title=None)
    y = alt.Y("value:Q", title=y_title, axis=alt.Axis(format="%"), scale=alt.Scale(zero=True))
    tooltip = [alt.Tooltip("date:T", title="Month", format="%Y-%m"),
               alt.Tooltip("series:N", title="Series"),
               alt.Tooltip("value:Q", title="Share", format=".1%")]
    raw = long[long["series"] == domain[0]]
    smooth = long[long["series"] == domain[1]]
    layers = [
        alt.Chart(raw).mark_line(strokeWidth=1).encode(x=x, y=y, color=color, tooltip=tooltip),
        alt.Chart(smooth).mark_line(strokeWidth=2.5).encode(x=x, y=y, color=color, tooltip=tooltip),
    ]
    if forecast is not None and not forecast.empty:
        fc_tooltip = [alt.Tooltip("date:T", title="Target month", format="%Y-%m"),
                      alt.Tooltip("value:Q", title="Forecast", format=".1%"),
                      alt.Tooltip("low:Q", title="Band low", format=".1%"),
                      alt.Tooltip("high:Q", title="Band high", format=".1%")]
        layers.append(alt.Chart(forecast).mark_rule(strokeWidth=3).encode(
            x=x, y=alt.Y("low:Q", title=y_title), y2="high:Q", color=color, tooltip=fc_tooltip))
        layers.append(alt.Chart(forecast).mark_point(filled=True, size=90, opacity=1).encode(
            x=x, y=y, color=color, tooltip=fc_tooltip))
    if outcome is not None and not outcome.empty:
        out_tooltip = [alt.Tooltip("date:T", title="Target month", format="%Y-%m"),
                       alt.Tooltip("value:Q", title="What happened", format=".1%")]
        layers.append(alt.Chart(outcome).mark_point(
            shape="diamond", filled=True, size=140, opacity=1, stroke="white", strokeWidth=1
        ).encode(x=x, y=y, color=color, tooltip=out_tooltip))
    return alt.layer(*layers).properties(height=340)


def skill_chart(skill_hist: pd.DataFrame, fc_row: dict | None, fc_month: str, labels: list[str],
                dark: bool, outcome_value: float | None = None) -> alt.Chart:
    """History up to the as-of month, plus the forecast at fc_month and, in an as-of view,
    the actual value there. labels = [monthly, smoothed, forecast, what happened]."""
    mode = "dark" if dark else "light"
    domain, colors = list(labels[:2]), [MUTED_GREY, SERIES_BLUE[mode]]
    if fc_row is not None:
        domain.append(labels[2])
        colors.append(SERIES_ORANGE[mode])
    if outcome_value is not None:
        domain.append(labels[3])
        colors.append(SERIES_AQUA[mode])
    hist = skill_hist.assign(date=pd.to_datetime(skill_hist["month"] + "-01"))
    long = pd.concat([
        hist[["date"]].assign(series=labels[0], value=hist["share"].to_numpy()),
        hist[["date"]].assign(series=labels[1], value=hist["share_smooth"].to_numpy()),
    ])
    forecast = None
    if fc_row is not None:
        forecast = pd.DataFrame([{"date": pd.Timestamp(fc_month + "-01"), "series": labels[2],
                                  "value": fc_row["value_12m"], "low": fc_row["low"],
                                  "high": fc_row["high"]}])
    outcome = None
    if outcome_value is not None:
        outcome = pd.DataFrame([{"date": pd.Timestamp(fc_month + "-01"), "series": labels[3],
                                 "value": outcome_value}])
    return line_chart(long, forecast, domain, colors,
                      "Share of job posts that mention the skill", outcome)


# --------------------------------------------------------------------------------------
# Sidebar helpers
# --------------------------------------------------------------------------------------

def show_refresh_result(result: dict, current: dict) -> None:
    """Render the stored result of the last click on 'Refresh live data'."""
    if result.get("busy") or "already running" in str(result.get("error") or ""):
        st.info(BUSY_NOTE)
        return
    if not result.get("ok"):
        st.error(f"Refresh failed: {result.get('error') or 'unknown error'}")
        fb = result.get("fallback") or {}
        st.write(
            "The last good data is shown: data as of "
            f"{fb.get('as_of') or current.get('as_of') or NA}, generated "
            f"{fb.get('generated_at') or current.get('generated_at') or NA}."
        )
        return
    before, after = result.get("posts_before"), result.get("posts_after")
    before_text = "new thread" if before is None else before
    st.success(f"Refreshed {result.get('month') or NA}: posts {before_text} -> {after}.")
    st.write(f"Fetched at {result.get('fetched_at') or NA}.")
    if result.get("shared_note"):
        st.caption(result["shared_note"])
    if result.get("scores_updated") is False:
        st.warning("The thread was updated, but the scores were not rebuilt: "
                   f"{result.get('scores_error') or 'unknown error'}. Old scores are shown.")
    changed = result.get("skills_changed") or {}
    if changed:
        with st.expander(f"Changed skills ({len(changed)})"):
            for skill, pair in changed.items():
                old, new = (list(pair) + [None, None])[:2]
                st.write(f"{skill}: {pct(old)} -> {pct(new)}")
    elif result.get("scores_updated"):
        st.write("No skill's share changed.")


# --------------------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------------------

# A session starts on the newest data in the shared store, if it is newer than the committed files.
st.session_state.setdefault("data_dir", live.start_dir(DEFAULT_DATA_DIR))
st.session_state.setdefault("refresh_result", None)
st.session_state.setdefault("live_fetched_at", None)


def active_data_dir() -> Path:
    chosen = st.session_state.get("data_dir")
    return Path(chosen) if chosen else DEFAULT_DATA_DIR


def using_runtime_folder() -> bool:
    """True when the scores come from a refreshed runtime folder, not the committed data/ folder."""
    chosen = st.session_state.get("data_dir")
    return bool(chosen) and Path(chosen).resolve() != DEFAULT_DATA_DIR.resolve()


def load_active() -> tuple[Path, Path, dict]:
    """(data folder, scores file, scores dict) for the folder the app currently reads."""
    folder = active_data_dir()
    scores_path = default_scores_path(folder)
    return folder, scores_path, load_scores(str(scores_path), scores_path.stat().st_mtime)


data_dir, scores_path, scores = load_active()
latest_as_of = scores.get("as_of")
is_fixture = scores.get("fixture") is True

# Sidebar layout: containers keep the visual order while the code handles Refresh first,
# so a successful refresh can reset the As-of slider before the slider is created.
with st.sidebar:
    st.header("Controls")
    scenario_box = st.container()
    asof_box = st.container()
    refresh_box = st.container()

if not is_fixture:
    with refresh_box:
        st.divider()
        if st.button("Refresh live data", help="Download the newest Hacker News hiring thread "
                                               "and rebuild the scores."):
            try:
                import engine.refresh as refresh_mod

                with st.spinner("Fetching the newest hiring thread and rebuilding the scores..."):
                    result = refresh_mod.refresh()
            except Exception as exc:  # the refresh function itself never raises; this is the import
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            result["shared_note"] = live.publish(result)  # one click helps every visitor
            st.session_state["refresh_result"] = result
            if result.get("ok") and result.get("data_dir"):
                st.session_state["data_dir"] = result["data_dir"]
                st.session_state["live_fetched_at"] = result.get("fetched_at")
                st.session_state.pop("as_of_view", None)  # back to the newest month
                data_dir, scores_path, scores = load_active()
                latest_as_of = scores.get("as_of")
        if using_runtime_folder() and st.button(
                "Back to committed snapshot",
                help="Drop the refreshed data in this session and show the committed files again."):
            st.session_state["data_dir"] = None
            st.session_state["live_fetched_at"] = None
            st.session_state["refresh_result"] = None
            st.session_state.pop("as_of_view", None)
            st.rerun()
        if live.start_dir(DEFAULT_DATA_DIR) and st.button(
                "Reload data", help="Check the shared store for newer data."):
            st.session_state["data_dir"] = live.reload(DEFAULT_DATA_DIR)
            st.session_state.pop("as_of_view", None)
            st.rerun()
        if st.session_state["refresh_result"]:
            show_refresh_result(st.session_state["refresh_result"], scores)

params = scores.get("scenario_params") or {}
k_text = params.get("k", NA)
scenario_labels = {"moderate": "Moderate",
                   "fast": f"Fast AI disruption (k = {k_text}, an assumption)"}
with scenario_box:
    scenario = st.radio("Scenario", SCENARIO_KEYS, index=0, format_func=scenario_labels.get)
scenario_label = scenario_labels[scenario]

# As-of view
interval = scores.get("interval") or {}
earliest = interval.get("earliest_supported_as_of")
view = scores
view_as_of = latest_as_of
if not is_fixture and earliest and latest_as_of and earliest < latest_as_of:
    options = [str(p) for p in pd.period_range(earliest, latest_as_of, freq="M")]
    if st.session_state.get("as_of_view") not in options:
        st.session_state.pop("as_of_view", None)
    with asof_box:
        chosen_as_of = st.select_slider(
            "As of", options=options, value=latest_as_of, key="as_of_view",
            help="Rerun the engine with only the data known at that month.")
    if chosen_as_of != latest_as_of:
        demand_path = data_dir / "demand_monthly.csv"
        try:
            with st.spinner(f"Recomputing with data up to {chosen_as_of} "
                            "(a few seconds the first time)..."):
                view = scores_as_of(str(data_dir), chosen_as_of, demand_path.stat().st_mtime)
            view_as_of = chosen_as_of
        except (ValueError, OSError, KeyError) as exc:
            st.sidebar.error(f"Could not compute {chosen_as_of}: {exc}. Showing the latest month.")
skills = view.get("skills") or []
band_label = (view.get("interval") or {}).get("label") or "target band"
past_view = view_as_of != latest_as_of

# --------------------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------------------

st.title("Verity")
st.subheader("Future-ready skills for tech developers")
st.markdown(f"**Data as of:** {view.get('as_of') or NA} | generated {view.get('generated_at') or NA}")
model_name = (view.get("interval") or {}).get("model")
if model_name:
    words = f" ({MODEL_WORDS[model_name]})" if model_name in MODEL_WORDS else ""
    st.markdown(f"Forecast model: {model_name}{words}, {band_label}")
if using_runtime_folder():
    committed = read_json(DEFAULT_DATA_DIR / SCORES_NAME) or {}
    stored = live.folder_meta(data_dir)
    if stored:
        st.info(live.banner(stored, committed.get("generated_at")))
    else:
        st.info(f"Live refresh at {st.session_state.get('live_fetched_at') or NA}. Held only on this server until "
                f"it restarts; the committed snapshot is dated {committed.get('generated_at') or NA}.")
if view.get("partial_month") is True:
    st.info(PARTIAL_NOTE)
if past_view:
    st.info(f"Looking back: this view uses only data up to {view_as_of}. "
            "The data folder is not changed.")
if is_fixture:
    st.warning(FIXTURE_BANNER)
st.markdown("Estimates, not facts. You decide.")
st.markdown("No LLM is used in this view.")
try:
    shown_file = scores_path.relative_to(BASE_DIR).as_posix()
except ValueError:
    shown_file = str(scores_path)
st.caption(f"File: {shown_file} | scenario: {scenario_label}")

# --------------------------------------------------------------------------------------
# Data shared by the tabs
# --------------------------------------------------------------------------------------

demand = read_csv(data_dir / "demand_monthly.csv") if not is_fixture else None
taxonomy = read_json(data_dir / "taxonomy.json") if not is_fixture else None
category_of = {t.get("skill"): t.get("category") for t in taxonomy or [] if isinstance(t, dict)}
backtest = read_json(data_dir / "backtest.json") if not is_fixture else None


def read_static(name: str, reader):
    """A file that the refresh does not rewrite: look in the active folder, then in data/."""
    for folder in (data_dir, DEFAULT_DATA_DIR):
        value = reader(folder / name)
        if value is not None:
            return value
    return None


# Exposure cross-check (engine/exposure_indices.py, engine/k_estimate.py). Missing files hide it.
exposure_agreement = read_static("exposure_agreement.json", read_json) if not is_fixture else None
k_estimate = read_static("k_estimate.json", read_json) if not is_fixture else None
_robust = read_static("exposure_robustness.csv", read_csv) if not is_fixture else None
contested_skills = (
    set(_robust.loc[_robust["stance_robust"].astype(str).str.lower() == "false", "skill"])
    if _robust is not None and {"skill", "stance_robust"} <= set(_robust.columns) else set())


tab_roles, tab_pathway, tab_skills, tab_detail, tab_method = st.tabs(
    ["Roles", "Pathway", "Skills", "Skill detail", "Method"])

# --------------------------------------------------------------------------------------
# Tab: Roles
# --------------------------------------------------------------------------------------

def role_card(role: dict, position: int, sort_by_match: bool, show_fast: bool) -> None:
    """One bordered card for one ranked role. Every number comes from engine.roles.match_roles."""
    with st.container(border=True):
        title = f"#{position} {role['name']}"
        if sort_by_match:
            title += f" (rank #{role['rank']} by rank score)"
        st.markdown(f"### {title}")
        st.progress(min(max(role["match_score"], 0.0), 1.0), text=f"Match {role['match_score']:.0%}")

        outlook = role["outlook"]
        label = outlook.get("trend_label")
        if label and outlook.get("share_last12") is not None and outlook.get("share_prev12") is not None:
            p_text = f", p = {outlook['trend_p']:.3f}" if _is_number(outlook.get("trend_p")) else ""
            st.markdown(f"Role demand: {TREND_BADGE.get(label, label)} "
                        f"{outlook['share_last12']:.1%} of posts in the last 12 months vs "
                        f"{outlook['share_prev12']:.1%} the 12 months before{p_text}")
        else:
            st.markdown("Role demand: :gray-badge[No label] too few posts to label a trend")

        left, right = st.columns(2)
        with left:
            st.markdown("**You have**")
            st.markdown("\n".join(f"- {s['skill']} (weight {s['weight']:.0%})" for s in role["have"]) or "- none")
        with right:
            st.markdown("**Gaps**")
            st.markdown("\n".join(
                f"- {s['skill']} (weight {s['weight']:.0%}; status {s['status'] or NA}; "
                f"trend {s['trend_label'] or NO_LABEL})" for s in role["gap"]) or "- none")

        st.write(role["reason"])
        confidence = f"Confidence: {role['tier']} ({role['n_single_role_posts']} single-role posts)"
        if role["tier"] == "rough":
            confidence += ". Rough profile: treat the weights as approximate."
        st.caption(confidence)
        st.caption("SDG: " + (", ".join(str(t) for t in role["sdg"]) if role["sdg"] else NA))
        if show_fast:
            st.caption(f"Fast AI scenario (estimate): about {role['fast_shift']:+.1%} role demand vs moderate. "
                       "Does not change the ranking.")
        if st.button("Choose this as my target role", key=f"target_{role['role_id']}"):
            st.session_state["target_role"] = role["name"]


def roles_tab() -> dict | None:
    """The Roles tab: profile intake, ranked role cards, formula, sources.

    Returns the match_roles output, so the Pathway tab uses the same profile, skills and as-of month.
    Returns None when the role data is missing for this view.
    """
    role_dir = DEFAULT_DATA_DIR
    if is_fixture or taxonomy is None or not all((role_dir / n).exists() for n in ROLE_FILES):
        st.info("Role match needs the real data files (taxonomy, roles, role profiles, role demand, exposure). "
                "They are not available in this view.")
        return None
    import engine.roles as roles_mod

    st.subheader("Which future roles fit you?")
    st.caption("Pick an example profile (synthetic people, not real CVs) and edit the skills. A CV upload comes later.")
    persona = st.selectbox("Example profile", list(PERSONAS), key="role_persona")
    if st.session_state.get("role_persona_applied") != persona:  # a new persona resets the skill list
        st.session_state["role_skills"] = list(PERSONAS[persona])
        st.session_state["role_persona_applied"] = persona
    skill_options = [t["skill"] for t in taxonomy if isinstance(t, dict) and t.get("skill")]
    my_skills = st.multiselect("Your skills (add or remove)", skill_options, key="role_skills")
    sort_by_match = st.toggle("Sort by match only", key="roles_sort_match",
                              help="Off: sorted by rank score (match and outlook).")
    target_box = st.container()

    try:
        profile = roles_mod.profile_for(view_as_of, read_json(role_dir / "role_profiles.json"))
    except ValueError as exc:
        st.info(f"No role profile for {view_as_of}: {exc}.")
        return None
    demand_path, roles_path = role_dir / "role_demand_monthly.csv", role_dir / "roles.json"
    trends = role_trends_as_of(str(demand_path), str(roles_path), view_as_of, demand_path.stat().st_mtime)
    out = roles_mod.match_roles(set(my_skills), profile, view, trends, scenario,
                                exposure=roles_mod.load_exposure(role_dir / "exposure.csv"))

    ranked, low_match = out["roles"], out["low_match"]
    limit = out["formula"]["low_match_below"]
    if ranked:
        shown = sorted(ranked, key=lambda r: (-r["match_score"], r["rank"])) if sort_by_match else ranked
        for position, role in enumerate(shown, start=1):
            role_card(role, position, sort_by_match, show_fast=scenario == "fast")
        if low_match:
            with st.expander(f"Not a fit yet (under {limit:.0%} match)"):
                st.caption("These roles are not ranked: with so few of their skills, the outlook alone "
                           "should not put them on the list.")
                for role in low_match:
                    st.markdown(f"**{role['name']}**: match {role['match_score']:.0%}")
                    st.markdown("\n".join(
                        f"- {s['skill']} (weight {s['weight']:.0%}; status {s['status'] or NA}; "
                        f"trend {s['trend_label'] or NO_LABEL})" for s in role["gap"]) or "- no gaps")
                    if st.button("Choose this as my target role", key=f"target_{role['role_id']}"):
                        st.session_state["target_role"] = role["name"]
    else:
        st.info("None of the roles match well yet; pick a target to see the gap")
        for position, role in enumerate(low_match, start=1):  # sorted by match, not ranked
            role_card(role, position, False, show_fast=scenario == "fast")

    chosen = st.session_state.get("target_role")
    target_box.markdown(f"**Target role:** {chosen}" if chosen else "**Target role:** none chosen yet")
    for item in out["not_ranked"]:
        st.caption(f"{item['name']}: {item['note']}")
    if out["unmatched"]:
        st.caption("Skills not in the taxonomy (ignored): " + ", ".join(out["unmatched"]))

    n_posts = sum(r["n_single_role_posts"] for r in profile["roles"] if r["ranked"])
    win = profile["window"]
    st.caption(f"Role skill weights learned from {n_posts:,} single-role HN 'Who is hiring?' posts, "
               f"{win['from']} to {win['to']}. Role demand from monthly shares to {trends['as_of']}.")
    with st.expander("How the rank is computed"):
        formula = out["formula"]
        st.markdown(
            "- **Match score** = weight of the role's skills you have / total weight of its skills. "
            "Weights are learned from real posts: the share of the role's single-role posts that mention the "
            "skill, kept when the role asks for it at least 1.1 times as often as the average post.\n"
            "- **Outlook score** = 1.0 if the role's share of posts is Rising, 0.5 if No clear change or unknown, "
            "0.0 if Falling (same Welch test as the skill labels).\n"
            f"- **Rank score** = {formula['match_weight']} x match + {formula['future_weight']} x outlook. "
            "0.7 / 0.3 are team judgement, not fitted to data.\n"
            "- **Fast AI scenario** only adds an estimate of how the role's demand moves "
            f"(-k x sum of weight x AI exposure, k = {formula['k']}, an assumption). It never changes the ranking.\n"
            "- Having TypeScript counts as having JavaScript / TypeScript. Roles with fewer than 50 single-role "
            "posts are not ranked; a profile with fewer than 150 posts or fewer than 5 skills is marked rough.\n"
            f"- A role with under {formula['low_match_below']:.0%} match is not ranked (team judgement), so "
            "it cannot rank on its outlook alone. It is listed under \"Not a fit yet\".")
    return out


with tab_roles:
    role_out = roles_tab()

# --------------------------------------------------------------------------------------
# Tab: Pathway
# --------------------------------------------------------------------------------------

def next_monday(today: date) -> date:
    """The first Monday after `today` (a Monday gives the Monday a week later)."""
    return today + timedelta(days=7 - today.weekday())


def clear_target_role() -> None:
    st.session_state.pop("target_role", None)


def change_target_button() -> None:
    """Link-style button. Choosing a role stays possible only in the Roles tab."""
    st.button("Change target role", key="change_target_role", type="tertiary", on_click=clear_target_role,
              help="Clears the target. Pick a new one in the Roles tab.")


def step_card(step: dict) -> None:
    """One skill of the plan: reason, resource, deadline, source. SDG tags sit in the SDG section."""
    res = step["resource"]
    with st.container(border=True):
        st.markdown(f"**{step['order']}. {step['skill']}**")
        st.markdown(f"Why: {step['reason']}")
        if res:
            st.markdown(f"Resource: [{res['title']}]({res['url']}) | {res['provider']} | cost: {res['cost']} | "
                        f"about {step['minutes']} minutes (estimate)")
        else:
            st.markdown(f"Resource: {step['resource_note']}")
            st.caption("No tasks are planned for this skill until a verified resource is added.")
        if step["deadline"]:
            st.markdown(f"Step deadline: {step['deadline']}")
        st.caption(f"Source: {step['source']}")


def todo_table(tasks: list[dict], sig: str, today: date) -> list[str]:
    """One row per task with a checkbox. Returns the ids that are ticked."""
    before = (set(st.session_state.get("done_tasks") or [])
              if st.session_state.get("done_plan_sig") == sig else set())
    widths = [0.7, 1.9, 0.9, 6, 1.2]
    head = st.columns(widths)
    for col, text in zip(head, ("Done", "Date", "Minutes", "Task", "Link")):
        col.markdown(f"**{text}**")
    ticked = []
    for t in tasks:
        c_done, c_date, c_min, c_task, c_link = st.columns(widths, vertical_alignment="center")
        done = c_done.checkbox(f"Done: {t['title']}", value=t["id"] in before,
                               key=f"done_{sig}_{t['id']}", label_visibility="collapsed")
        if done:
            ticked.append(t["id"])
        overdue = not done and date.fromisoformat(t["date"]) < today
        c_date.markdown(f"{t['date']} (overdue)" if overdue else t["date"])
        c_min.markdown(str(t["minutes"]))
        c_task.markdown(f"~~{t['title']}~~" if done else t["title"])
        c_link.markdown(f"[Open]({t['resource_url']})")
    return ticked


def pathway_tab(role_out: dict | None) -> None:
    """The Pathway tab: staged plan, daily to-do list with progress, exports, SDG links."""
    from engine.pathway import (HRD_CORP_NOTE, PLACEHOLDER_RESOURCE, build_pathway, progress, sdg_headline,
                                tasks_signature, to_ics, to_markdown, today_myt)

    st.session_state.setdefault("done_tasks", [])
    target = st.session_state.get("target_role")
    if not target:
        st.info(NO_TARGET_PROMPT)
        return
    st.subheader(f"Pathway to {target}")
    change_target_button()
    resources_doc = read_json(DEFAULT_DATA_DIR / "resources.json")
    if role_out is None or resources_doc is None or taxonomy is None:
        st.info("The pathway needs the real data files (roles, taxonomy, resources). They are not available in this view.")
        return
    everyone = role_out["roles"] + role_out["low_match"]
    role = next((r for r in everyone if r["name"] == target), None)
    if role is None:
        st.warning(f"{target} is not in the role list for this view (as of {view_as_of}). Change the target role.")
        return
    if not role["gap"]:
        st.success(f"You already have every skill in the {target} profile, so there is no gap to plan.")
        return

    left, right = st.columns(2)
    hours = left.number_input("Hours per week", min_value=1, max_value=40, value=5, step=1, key="pathway_hours")
    today = today_myt()  # Malaysia time (UTC+8)
    start = right.date_input("Start date", value=next_monday(today), key="pathway_start")
    start = start if isinstance(start, date) else next_monday(today)

    # The no-regret stage counts the target role and every ranked role (match 20% or more), each once.
    role_gaps = [role["gap"]] + [r["gap"] for r in role_out["roles"] if r["name"] != target]
    plan = build_pathway(target, role["gap"], role_gaps, view, resources_doc,
                         scenario=scenario, hours_per_week=hours, start_date=start, taxonomy=taxonomy)
    st.caption(f"Skill data as of {plan['skill_scores_as_of'] or NA}. Scenario: {plan['scenario_label']}. "
               f"{plan['totals']['steps']} skills, {plan['totals']['tasks']} daily tasks, about "
               f"{plan['totals']['hours']} hours (estimate), {hours} hours a week, Monday to Friday.")
    st.info(f"HRD Corp: {resources_doc.get('hrd_corp_note') or HRD_CORP_NOTE}")
    if scenario == "fast":
        st.info("Fast AI scenario (an assumption, not a forecast): future bets (Stage 3) are moved earlier, to "
                "second place, ahead of near-term demand. Only the order of the stages changes.")

    # Stages
    for stage in plan["stages"]:
        st.markdown(f"### {stage['label']}")
        steps = [s for s in plan["steps"] if s["stage"] == stage["name"]]
        if not steps:
            st.caption("No skills in this stage.")
        for step in steps:
            step_card(step)
    if plan["unresolved"]:
        st.caption(f"{PLACEHOLDER_RESOURCE}: {', '.join(plan['unresolved'])}.")

    # Daily to-do list
    st.markdown("### Daily to-do list")
    sig = tasks_signature(plan["tasks"])  # a tick belongs to this exact task list, not to the settings
    progress_box = st.container()  # filled after the checkboxes, so it shows this run's ticks
    if plan["tasks"]:
        ticked = todo_table(plan["tasks"], sig, today)
    else:
        ticked = []
        st.info("No daily tasks yet: no skill in this gap has a verified resource.")
    st.session_state["done_tasks"] = ticked
    st.session_state["done_plan_sig"] = sig
    prog = progress(plan["tasks"], ticked, today)
    with progress_box:
        st.progress(min(max(prog["percent_done"] / 100, 0.0), 1.0),
                    text=f"{prog['percent_done']:.0f}% done ({prog['tasks_done']} of {prog['tasks_total']} tasks, "
                         f"{prog['minutes_done']} of {prog['minutes_total']} minutes)")
        n_over = len(prog["overdue"])
        st.markdown(f"Overdue as of {prog['as_of']}: {n_over} task{'' if n_over == 1 else 's'}")
        nxt = prog["next_task"]
        if nxt:
            st.markdown(f"Next task: {nxt['title']} ({nxt['minutes']} min, {nxt['date']})")
        else:
            st.markdown("Next task: none left" if plan["tasks"] else "Next task: none")
        done_skills = prog["completed_skills"] if plan["tasks"] else []
        st.markdown("Skills completed: " + (", ".join(done_skills) if done_skills else "none yet"))
        st.markdown(f"Plan finishes on {plan['finish_date']}" if plan["finish_date"]
                    else "Plan finishes on: no dated tasks")
    st.caption("Ticks are kept while the task list stays exactly the same. Any change to the tasks (role, skills, "
               "scenario, pace or start date) makes a new plan and clears them. Times are estimates.")

    # Exports: the browser downloads the text. The server writes no file.
    st.markdown("### Export")
    e1, e2 = st.columns(2)
    e1.download_button("Download plan (Markdown)", to_markdown(plan), file_name="verity_plan.md",
                       mime="text/markdown", key="download_plan_md", on_click="ignore")
    e2.download_button("Download calendar (.ics)", to_ics(plan["tasks"]), file_name="verity_plan.ics",
                       mime="text/calendar", key="download_plan_ics", on_click="ignore")

    # SDG links: the plan-level statements first, the per-skill tags second
    st.markdown("### SDG links")
    for sentence in sdg_headline(plan, role["outlook"]):
        st.markdown(sentence)
    with st.expander("SDG tags per skill"):
        for step in plan["steps"]:
            if step["sdg"]:
                st.markdown(f"- {step['skill']}: SDG {', '.join(step['sdg'])}. {step['sdg_reason'] or ''}".rstrip())
    st.caption(plan["notes"][0])  # the estimate note; the HRD Corp note is shown once, above


with tab_pathway:
    pathway_tab(role_out)

# --------------------------------------------------------------------------------------
# Tab: Skills
# --------------------------------------------------------------------------------------

with tab_skills:
    if not skills:
        st.info("No skills in the data file.")
    else:
        status_options = sorted({s.get("status") or NA for s in skills})
        trend_options = sorted({s.get("trend_label") or NO_LABEL for s in skills})
        category_options = sorted({category_of.get(s.get("skill")) or NA for s in skills})
        f1, f2, f3 = st.columns(3)
        with f1:
            status_pick = st.multiselect("Status", status_options, default=status_options)
        with f2:
            trend_pick = st.multiselect("Trend label", trend_options, default=trend_options)
        with f3:
            category_pick = st.multiselect("Category", category_options, default=category_options)

        rows = []
        for s in skills:
            status = s.get("status") or NA
            trend = s.get("trend_label") or NO_LABEL
            category = category_of.get(s.get("skill")) or NA
            if status not in status_pick or trend not in trend_pick or category not in category_pick:
                continue
            rows.append({
                "Skill": s.get("skill") or NA,
                "Category": category,
                "Status": status,
                "Trend label (mentions last 12 vs prior 12)": trend_text(s),
                "Share now": share_text(s),
                f"12-month forecast, {scenario_labels[scenario].split(' (')[0]} (low to high)":
                    forecast_text(s, scenario),
                "AI stance": s.get("stance") or NA,
                "SDG": sdg_text(s),
                "Note": s.get("note") or "",
            })
        st.caption(f"Showing {len(rows)} of {len(skills)} skills. "
                   "The forecast is the share of job posts 12 months after the as-of month, "
                   f"with its {band_label}.")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Trend label is observed (last 12 months against the 12 before), not a forecast. "
                   "n/a means the data volume is too low for a forecast.")

# --------------------------------------------------------------------------------------
# Tab: Skill detail
# --------------------------------------------------------------------------------------

with tab_detail:
    if not skills:
        st.info("No skills in the data file.")
    else:
        names = [s.get("skill") or NA for s in skills]
        picked = st.selectbox("Skill", names, key="detail_skill")
        skill = skills[names.index(picked)]
        status = skill.get("status")
        fc = get_forecast(skill, scenario)
        moderate = get_forecast(skill, "moderate")
        has_forecast = (status is None or status == "ok") and _is_number(fc.get("value_12m"))
        has_moderate = (status is None or status == "ok") and _is_number(moderate.get("value_12m"))
        target_month = month_add(view_as_of, HORIZON_MONTHS) if view_as_of else None
        scenario_short = scenario_label.split(" (")[0]

        # What happened: graded against the Moderate band, the one the backtest calibrated, on
        # the single target month (the same quantity the backtest uses).
        outcome = None
        outcome_text = None
        target_row = None
        if past_view and target_month and demand is not None:
            target_rows = demand[(demand["skill"] == picked) & (demand["month"] == target_month)]
            if target_rows.empty:
                outcome_text = f"{target_month} is not in the data yet, so the outcome is not known."
            elif not has_moderate:
                outcome_text = ("No forecast was made for this skill at that date, "
                                "so there is nothing to compare.")
            else:
                from engine.outcome import band_verdict

                target_row = target_rows.iloc[0]
                outcome = band_verdict(moderate, target_row["mentions"], target_row["n_posts"])

        st.subheader(picked)
        if has_forecast and target_month:
            st.write(f"Forecast for {target_month} ({scenario_label}): {pct(fc['value_12m'])}, "
                     f"{band_label} {pct(fc.get('low'))} to {pct(fc.get('high'))}.")
        elif skill.get("note"):
            st.write(skill["note"])

        if demand is not None and view_as_of:
            # Only months up to the as-of month are drawn. The one exception is the outcome point.
            hist = demand[(demand["skill"] == picked) & (demand["month"] <= view_as_of)]
            hist = hist.sort_values("month")
            if hist.empty:
                st.info("No monthly history for this skill in the data folder.")
            else:
                labels = ["Monthly share", "3-month smoothed",
                          f"Forecast {target_month} ({scenario_short}) with band", "What happened"]
                st.altair_chart(
                    skill_chart(hist, fc if has_forecast else None, target_month, labels,
                                is_dark_theme(), outcome["actual"] if outcome else None),
                    width="stretch")
                st.caption("Share of the month's job posts that mention the skill (Hacker News "
                           "'Who is hiring?'). The smoothed line is the mean of the last 3 months."
                           + (f" The point and bar at the right are the forecast and its {band_label}."
                              if has_forecast else "")
                           + (" The diamond is what happened." if outcome else ""))
        else:
            st.info("The monthly history is not available for the sample data.")

        # Trend label
        label = skill.get("trend_label")
        m12, p12 = skill.get("mentions_last12"), skill.get("posts_last12")
        mprev, pprev = skill.get("mentions_prev12"), skill.get("posts_prev12")
        if all(_is_number(v) for v in (m12, p12, mprev, pprev)):
            p_value = skill.get("trend_p")
            p_text = f", p = {p_value:.3f}" if _is_number(p_value) else ""
            head = label if label else "No trend label (too few mentions)"
            st.markdown(
                f"**Trend label: {head}.** Last 12 months: {m12} mentions in {p12} posts "
                f"({pct(m12 / p12 if p12 else None)}). The 12 months before: {mprev} mentions in "
                f"{pprev} posts ({pct(mprev / pprev if pprev else None)}){p_text}. "
                "This is observed, not a forecast.")

        # Scenario shift. The band is asymmetric, so "inside" means low <= Fast value <= high.
        shift, width = skill.get("scenario_shift_pp"), skill.get("band_width_pp")
        fast_value = get_forecast(skill, "fast").get("value_12m")
        if _is_number(shift) and _is_number(width):
            low, high = moderate.get("low"), moderate.get("high")
            if _is_number(fast_value) and _is_number(low) and _is_number(high):
                verdict = ("inside the Moderate band" if low <= fast_value <= high
                           else "outside the Moderate band")
                verdict_text = f" The Fast forecast is {verdict} ({pct(low)} to {pct(high)})."
            else:
                verdict_text = ""
            st.markdown(
                f"**Fast scenario shift:** {signed_pp(shift)} against the Moderate forecast, next "
                f"to a band width of {width:.1f} pp.{verdict_text}")
        if skill.get("note"):
            st.markdown(f"**Note:** {skill['note']}")
        contested = " (contested across indices)" if picked in contested_skills else ""
        st.markdown(f"**AI stance:** {skill.get('stance') or NA}{contested} | **SDG:** {sdg_text(skill)}")

        # What happened (as-of views only)
        if past_view and target_month and demand is not None:
            st.subheader("What happened")
            if outcome is None:
                st.write(outcome_text)
            else:
                open_note = (" That month's thread was still open, so the number can change."
                             if scores.get("partial_month") is True and target_month == latest_as_of
                             else "")
                st.write(
                    f"Graded against the Moderate band (the calibrated one): {pct(moderate['low'])} "
                    f"to {pct(moderate['high'])}, from a forecast of {pct(moderate['value_12m'])} "
                    f"made at {view_as_of}. The actual {target_month} value, smoothed the same way "
                    f"as the model's input, was {pct(outcome['actual'])}. The actual value was "
                    f"{outcome['place']} the band.{open_note}")
                st.caption("The Fast band is an assumption and is not graded.")
                window = [month_add(target_month, -i) for i in (2, 1, 0)]
                rows_t = demand[(demand["skill"] == picked) & (demand["month"].isin(window))]
                reference = ""
                if len(rows_t) == len(window) and rows_t["n_posts"].sum() > 0:
                    m_sum, n_sum = int(rows_t["mentions"].sum()), int(rows_t["n_posts"].sum())
                    reference = (f" Pooled share over the 3 months ending {target_month}: "
                                 f"{pct(m_sum / n_sum)} ({m_sum}/{n_sum} posts).")
                st.caption(f"For reference only: {target_month} raw share "
                           f"{pct(float(target_row['share']))} "
                           f"({int(target_row['mentions'])}/{int(target_row['n_posts'])} posts)."
                           f"{reference}")

        # Sources
        st.subheader("Sources")
        sources = [src for src in (skill.get("sources") or []) if isinstance(src, dict)]
        if sources:
            for src in sources:
                name = src.get("name") or NA
                url = src.get("url") or ""
                date = src.get("date") or NA
                if url.startswith(("http://", "https://")):
                    st.markdown(f"- [{name}]({url}), {date}")
                elif url:
                    st.markdown(f"- {name} (file `{url}`), {date}")
                else:
                    st.markdown(f"- {name}, {date}")
        else:
            st.write(f"Sources: {NA}")
        evidence = skill.get("evidence") or []
        st.caption("Evidence IDs: " + (", ".join(str(e) for e in evidence) if evidence else NA))

# --------------------------------------------------------------------------------------
# Tab: Method
# --------------------------------------------------------------------------------------

def source_links(sources_md: str) -> list[tuple[str, str]]:
    """(title, first URL) for each numbered section of data/SOURCES.md."""
    found = []
    for block in re.split(r"(?m)^## ", sources_md)[1:]:
        title, _, body = block.partition("\n")
        if not re.match(r"\d+\.", title):
            continue
        url = re.search(r"https?://[^\s)>`,]+", body)
        if url:
            found.append((title.strip(), url.group(0).rstrip(".")))
    return found


def group_name(key: str) -> str:
    """Readable name for a backtest share-group key (lt_<n>pct, <a>_to_<b>pct, gt_<n>pct)."""
    if m := re.fullmatch(r"lt_(\d+)pct", key):
        return f"under {m.group(1)}%"
    if m := re.fullmatch(r"(\d+)_to_(\d+)pct", key):
        return f"{m.group(1)}% to {m.group(2)}%"
    if m := re.fullmatch(r"gt_(\d+)pct", key):
        return f"over {m.group(1)}%"
    return key


def signed(value) -> str:
    return f"{value:+.2f}" if _is_number(value) else NA


def gain_text(gain: dict, ci: list) -> str:
    """'+0.14 (+0.07 to +0.22)'; 'n/a' pieces when the file has no number; 'baseline' for naive."""
    if not gain:
        return "baseline"
    return f"{signed(gain.get('test_h12_mae_gain_pp'))} ({signed(ci[0])} to {signed(ci[1])})"


def mae_table(models: dict) -> pd.DataFrame:
    rows = []
    for name, m in models.items():
        early, test = m.get("early_mae_pp") or {}, m.get("test_mae_pp") or {}
        gain = m.get("test_h12_vs_naive") or {}
        ci = list(gain.get("ci95_skill_bootstrap") or []) + [None, None]
        rows.append({
            "Model": name,
            "Early h=1": early.get("h1"), "Early h=6": early.get("h6"), "Early h=12": early.get("h12"),
            "Test h=1": test.get("h1"), "Test h=6": test.get("h6"), "Test h=12": test.get("h12"),
            "Test h=12 gain vs naive (bootstrap CI)": gain_text(gain, ci),
            "In production": "yes" if m.get("in_production") else "no",
        })
    return pd.DataFrame(rows)


with tab_method:
    if backtest is None:
        st.info("data/backtest.json was not found, so the method tab has nothing to show. "
                "Run: python -m engine.backtest")
    else:
        origins = backtest.get("origins") or {}
        bt_to = (backtest.get("data_window") or {}).get("to") or NA
        st.header("How good is the forecast?")
        st.caption(f"Backtest numbers are computed on all data up to {bt_to}; they do not change "
                   "with the As-of slider.")
        st.write(
            f"We replayed history. At each origin month we forecast 1 to 12 months ahead and compared "
            f"with what happened. Early origins: {' to '.join(origins.get('early') or [NA])} "
            f"({origins.get('n_early', NA)} origins). Test origins: "
            f"{' to '.join(origins.get('test') or [NA])} ({origins.get('n_test', NA)} origins), "
            "used only for the scores below. Errors are mean absolute errors of the share, in "
            "percentage points (pp). Lower is better.")
        table = mae_table(backtest.get("models") or {})
        numeric = ["Early h=1", "Early h=6", "Early h=12", "Test h=1", "Test h=6", "Test h=12"]
        st.dataframe(table.style.format({c: "{:.2f}" for c in numeric}, na_rep=NA),
                     hide_index=True, width="stretch")
        st.subheader(f"Chosen model: {backtest.get('chosen_model') or NA}")
        if backtest.get("chosen_because"):
            st.write(backtest["chosen_because"])
        if backtest.get("verdict"):
            st.write(backtest["verdict"])

        cov = backtest.get("coverage") or {}
        interval_bt = backtest.get("interval") or {}
        st.header("How good is the band?")
        st.write(
            f"The {cov.get('label') or 'band'} covered {pct(cov.get('test_h12'))} of real values at "
            f"h=12 on the test origins (target {pct(cov.get('nominal'), 0)}), with a mean band width of "
            f"{pp_plain(cov.get('test_mean_band_width_h12_pp'))}. "
            "A coverage above the target means the band is wide, not tight. "
            f"Band type: {interval_bt.get('type') or NA}.")
        groups = cov.get("by_share_group") or {}
        if groups:
            st.dataframe(pd.DataFrame([
                {"Share group": group_name(key),
                 "Skill-origins": g.get("n_skill_origins"),
                 "Coverage at h=12": pct(g.get("h12")),
                 "Mean band width at h=12 (pp)": pp_plain(g.get("mean_band_width_h12_pp"), unit=False)}
                for key, g in groups.items()]), hide_index=True, width="stretch")
            if cov.get("share_group_definition"):
                st.caption(f"Share group: {cov['share_group_definition']}.")

        tl = backtest.get("trend_label_backtest") or {}
        st.header("How good is the trend label?")
        st.write(
            f"In the backtest the Rising or Falling label pointed the right way for the next 12 months "
            f"{pct(tl.get('trend_label_hit_rate'))} of the time (n = {tl.get('n', NA)} labelled "
            f"skill-origins). Rising: {pct(tl.get('hit_rate_rising'))} (n = {tl.get('n_rising', NA)}). "
            f"Falling: {pct(tl.get('hit_rate_falling'))} (n = {tl.get('n_falling', NA)}).")
        if tl.get("definition"):
            st.caption(tl["definition"])
        if tl.get("caveat"):
            st.caption(tl["caveat"])

        st.header("Caveats")
        for caveat in backtest.get("caveats") or []:
            st.markdown(f"- {caveat}")
        for note in scores.get("notes") or []:
            if note not in (backtest.get("caveats") or []):
                st.markdown(f"- {note}")

    if exposure_agreement:
        from engine.exposure_indices import agreement_text, correlation_text, crosscheck_rows

        st.header("Exposure cross-check")
        st.write(
            "Our AI stance comes from one source, the Anthropic Economic Index (AEI). We checked it against "
            "three other published indices at the occupation level. Each cell is the category's z-score "
            "(0 = average of the 40 skills) and the stance that source would give. The two GPTs variants "
            "and the two AIOE variants are averaged into one source each.")
        st.dataframe(pd.DataFrame(crosscheck_rows(exposure_agreement)), hide_index=True, width="stretch")
        if correlation_text(exposure_agreement):
            st.markdown(correlation_text(exposure_agreement))
        st.markdown(agreement_text(exposure_agreement))
        st.caption(
            "A polar stance (substitutable or complement) is supported by a source that puts the category on "
            "the same side of the average; a neutral stance, by a source that puts it near the average. "
            "'Contested' means that half or fewer of the sources support it. Eight occupations and four "
            "sources make this a sanity check, not a measurement. AEI and Microsoft measure chatbot "
            "use; GPTs and AIOE rate what a model could do, so some disagreement is expected.")
        if k_estimate:
            from engine.k_estimate import k_caption, k_line

            st.markdown(f"**k from data:** {k_line(k_estimate)}")
            st.caption(k_caption(k_estimate))

    ai_context = read_csv(data_dir / "ai_context_monthly.csv") if not is_fixture else None
    if ai_context is not None and not ai_context.empty:
        st.header("Share of job posts that mention AI at all (company context, not a skill)")
        ai_frame = ai_context.sort_values("month")
        if view_as_of:  # an as-of view shows only what was known then
            ai_frame = ai_frame[ai_frame["month"] <= view_as_of]
        ai_frame = ai_frame.assign(date=pd.to_datetime(ai_frame["month"] + "-01"))
        ai_labels = ["Monthly share", "3-month smoothed"]
        mode = "dark" if is_dark_theme() else "light"
        ai_long = pd.concat([
            ai_frame[["date"]].assign(series=ai_labels[0], value=ai_frame["share"].to_numpy()),
            ai_frame[["date"]].assign(series=ai_labels[1], value=ai_frame["share_smooth"].to_numpy()),
        ])
        st.altair_chart(
            line_chart(ai_long, None, ai_labels, [MUTED_GREY, SERIES_BLUE[mode]],
                       "Share of job posts that mention AI"),
            width="stretch")
        st.caption("Posts that only say 'AI' in a company blurb are counted here and not as a skill. "
                   "This is a signal about hiring context, not about one skill.")

    sources_path = data_dir / "SOURCES.md"
    if not sources_path.exists():
        sources_path = DEFAULT_DATA_DIR / "SOURCES.md"
    if sources_path.exists() and not is_fixture:
        st.header("Data sources")
        st.write("Full list with dates and licences: `data/SOURCES.md`.")
        for title, url in source_links(load_text(str(sources_path), sources_path.stat().st_mtime)):
            st.markdown(f"- [{title}]({url})")

    # New skills radar: data/skill_candidates.json from engine/discover.py. A person adds a skill to taxonomy.json.
    radar_path = data_dir / "skill_candidates.json"
    radar = read_json(radar_path if radar_path.exists() else DEFAULT_DATA_DIR / "skill_candidates.json")
    if radar and radar.get("candidates") and not is_fixture:
        st.header("Candidate new skills (not yet in Verity; need human review)")
        bt_main = (radar.get("backtest") or {}).get("main") or {}
        st.caption(
            f"Terms that look like tech names in Hacker News hiring posts up to {radar.get('as_of', NA)} and are not "
            "in the taxonomy. Shares are the share of posts in the last 12 months / the 12 months before. "
            "Growth is the first share divided by the second (a term absent before shows 'new since'). "
            "Nothing here changes the Skills tab until a person adds the skill to data/taxonomy.json. "
            f"Backtest at {bt_main.get('as_of', NA)}: {bt_main.get('hits', NA)} of the top {bt_main.get('top_n', NA)} "
            f"candidates grew in the next 12 months (all candidates: {pct(bt_main.get('base_rate_all_candidates'), 0)}). "
            f"{(radar.get('backtest') or {}).get('verdict', '')} Read the evidence before you decide.")
        radar_rows = []
        for c in radar["candidates"][:15]:
            links = [e.get("thread_url") for e in c.get("examples") or []] + [None, None]
            radar_rows.append({
                "Term": c.get("term"),
                "Share last 12 / prior 12 months": f"{pct(c.get('share_last'), 2)} / {pct(c.get('share_prior'), 2)}",
                "Growth": f"new since {c['new_since']}" if c.get("new_since") else f"x{c.get('growth')}",
                "Trend label": c.get("label") or NO_LABEL,
                "First seen": c.get("first_seen"),
                "Co-occurring skills": ", ".join(s["skill"] for s in c.get("co_occurring_skills") or []) or NA,
                "Source 1": links[0], "Source 2": links[1],
            })
        st.dataframe(
            pd.DataFrame(radar_rows), hide_index=True, width="stretch",
            column_config={k: st.column_config.LinkColumn(k, display_text="thread")
                           for k in ("Source 1", "Source 2")})
