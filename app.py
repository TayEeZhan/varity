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


@st.cache_data
def load_scores() -> tuple[dict, str]:
    """Return (scores, relative file path). Prefer engine output, fall back to fixture."""
    path = ENGINE_PATH if ENGINE_PATH.exists() else FIXTURE_PATH
    with path.open(encoding="utf-8") as fh:
        scores = json.load(fh)
    return scores, path.relative_to(BASE_DIR).as_posix()


def pct(value: float) -> str:
    return f"{value:.1%}"


scores, source_file = load_scores()
skills = scores["skills"]

# Sidebar
scenario_label = st.sidebar.radio("Scenario", list(SCENARIOS), index=0)
scenario = SCENARIOS[scenario_label]
st.sidebar.markdown("Predictions are estimates. You decide.")
st.sidebar.markdown("LLM: not used yet")

# Main page
st.title("Verity")
st.subheader("Future-ready skills for tech developers")

if scores.get("fixture") is True:
    st.warning("Prototype: showing sample data, not real forecasts.")

st.caption(
    f"File: {source_file} | as of {scores['as_of']} | "
    f"generated {scores['generated_at']} | k = {scores.get('scenario_params', {}).get('k')}"
)

st.header(f"Skills: {scenario_label} scenario")
rows = []
for s in skills:
    fc = s["forecast"][scenario]
    rows.append(
        {
            "Skill": s["skill"],
            "Latest demand share": pct(s["demand_share_latest"]),
            "12-month forecast": pct(fc["value_12m"]),
            "Low": pct(fc["low"]),
            "High": pct(fc["high"]),
            "AI exposure": pct(s["ai_exposure"]),
            "SDG tags": ", ".join(s["sdg"]),
        }
    )
st.dataframe(pd.DataFrame(rows), hide_index=True)
st.caption("Low and High are the forecast range for the chosen scenario.")

st.header("Sources")
if skills:
    choice = st.selectbox("Pick a skill", [s["skill"] for s in skills])
    selected = next(s for s in skills if s["skill"] == choice)
    fc = selected["forecast"][scenario]
    st.write(
        f"{choice}: {pct(fc['value_12m'])} in 12 months ({scenario_label}), "
        f"range {pct(fc['low'])} to {pct(fc['high'])}."
    )
    for src in selected["sources"]:
        st.markdown(f"- [{src['name']}]({src['url']}), {src['date']}")
    st.caption("Evidence IDs: " + ", ".join(selected["evidence"]))
else:
    st.info("No skills in the data file.")
