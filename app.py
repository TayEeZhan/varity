"""Verity: Streamlit front end for skill forecasts.

Reads data/skill_scores.json (engine output) when it exists, otherwise the
sample file data/fixtures/skill_scores.json.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Verity", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
ENGINE_PATH = BASE_DIR / "data" / "skill_scores.json"
FIXTURE_PATH = BASE_DIR / "data" / "fixtures" / "skill_scores.json"

SCENARIOS = {"Moderate": "moderate", "Fast disruption": "fast"}
NA = "n/a"


@st.cache_data
def load_scores(path: str, mtime: float) -> dict:
    """Read the scores file at `path`.

    `mtime` is not used in the body. It is an argument so that the cache key
    changes when the file is rewritten, which makes the cache refresh itself.
    """
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def active_scores_path() -> Path:
    """Prefer engine output, fall back to the fixture."""
    return ENGINE_PATH if ENGINE_PATH.exists() else FIXTURE_PATH


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def pct(value) -> str:
    """Format a share (0 to 1) as a percent with 1 decimal."""
    return f"{value:.1%}" if _is_number(value) else NA


def index_value(value) -> str:
    """Format an index (0 to 1) as a number with 2 decimals."""
    return f"{value:.2f}" if _is_number(value) else NA


def get_forecast(skill: dict, scenario: str) -> dict:
    """Return the forecast block for one scenario, or {} if it is missing."""
    forecast = skill.get("forecast")
    if not isinstance(forecast, dict):
        return {}
    fc = forecast.get(scenario)
    return fc if isinstance(fc, dict) else {}


# Sidebar
# The button is read before the data is loaded, so a click clears the cache
# first and the rerun reads the file again.
if st.sidebar.button("Reload data"):
    st.cache_data.clear()
    st.rerun()

path = active_scores_path()
source_file = path.relative_to(BASE_DIR).as_posix()
scores = load_scores(str(path), path.stat().st_mtime)
skills = scores.get("skills") or []

scenario_label = st.sidebar.radio("Scenario", list(SCENARIOS), index=0)
scenario = SCENARIOS[scenario_label]
st.sidebar.markdown("Predictions are estimates. You decide.")
st.sidebar.markdown("LLM: not used yet")

# Main page
st.title("Verity")
st.subheader("Future-ready skills for tech developers")
st.markdown(
    f"**Data as of:** {scores.get('as_of') or NA} | "
    f"generated {scores.get('generated_at') or NA}"
)

if scores.get("fixture") is True:
    st.warning("Prototype: showing sample data, not real forecasts.")

params = scores.get("scenario_params") or {}
st.caption(f"File: {source_file} | k = {params.get('k', NA)}")

st.header(f"Skills: {scenario_label} scenario")
rows = []
for s in skills:
    fc = get_forecast(s, scenario)
    sdg = s.get("sdg") or []
    rows.append(
        {
            "Skill": s.get("skill") or NA,
            "Latest demand share": pct(s.get("demand_share_latest")),
            "12-month forecast": pct(fc.get("value_12m")),
            "Low": pct(fc.get("low")),
            "High": pct(fc.get("high")),
            "AI exposure index (0-1)": index_value(s.get("ai_exposure")),
            "SDG tags": ", ".join(str(tag) for tag in sdg) if sdg else NA,
        }
    )
st.dataframe(pd.DataFrame(rows), hide_index=True)
st.caption("Low and High are the forecast range for the chosen scenario.")

st.header("Sources")
if skills:
    names = [s.get("skill") or NA for s in skills]
    idx = st.selectbox(
        "Pick a skill",
        range(len(skills)),
        format_func=lambda i: names[i],
    )
    selected = skills[idx]
    choice = names[idx]
    fc = get_forecast(selected, scenario)
    st.write(
        f"{choice}: {pct(fc.get('value_12m'))} in 12 months ({scenario_label}), "
        f"range {pct(fc.get('low'))} to {pct(fc.get('high'))}."
    )

    sources = [src for src in (selected.get("sources") or []) if isinstance(src, dict)]
    if sources:
        for src in sources:
            name = src.get("name") or NA
            date = src.get("date") or NA
            url = src.get("url")
            link = f"[{name}]({url})" if url else name
            st.markdown(f"- {link}, {date}")
    else:
        st.write(f"Sources: {NA}")

    evidence = selected.get("evidence") or []
    evidence_text = ", ".join(str(e) for e in evidence) if evidence else NA
    st.caption("Evidence IDs: " + evidence_text)
else:
    st.info("No skills in the data file.")
