"""Phases 2-7 of the dynamic forecast: nowcast, ledger, AI labeller."""
import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from engine import forecast, ledger, llm_labels, role_discover


# --- Phase 2: nowcast ----------------------------------------------------------------

def test_nowcast_blends_the_open_month_toward_the_month_before_by_post_count():
    m, n = [100, 5], [1000, 20]  # last month 10%, open month 25% on only 20 posts
    raw = forecast.nowcast_y(m, n, 0)
    blended = forecast.nowcast_y(m, n, 100)
    assert np.allclose(raw, forecast.logit(forecast.smoothed_share(m, n)))
    expected = (5 + 100 * forecast.smoothed_share(100, 1000) + 0.5) / (20 + 100 + 1)
    assert np.isclose(forecast.inv_logit(blended[-1]), expected)
    assert blended[0] == raw[0]  # only the open month moves


def test_nowcast_k_is_taken_from_the_nearest_cut_day(tmp_path):
    (tmp_path / "nowcast_backtest.json").write_text(json.dumps({"roles": {"k_by_day": {"1": 100, "3": 50, "7": 10, "14": 0}}}))
    assert forecast.load_nowcast_k(tmp_path, "roles", 0.2) == 100
    assert forecast.load_nowcast_k(tmp_path, "roles", 4) == 50
    assert forecast.load_nowcast_k(tmp_path, "roles", 25) == 0
    assert forecast.load_nowcast_k(tmp_path, "skills", 1) == 0  # missing kind: no blending
    assert forecast.load_nowcast_k(tmp_path / "nope", "roles", 1) == 0


def test_days_open_counts_from_the_thread_post_time():
    threads = pd.DataFrame([{"month": "2026-11", "created_at": "2026-11-02T15:00:00Z"}])
    assert forecast.days_open(threads, "2026-11", datetime(2026, 11, 5, 15, tzinfo=timezone.utc)) == 3
    assert forecast.days_open(threads, "2026-12", datetime(2026, 12, 5, tzinfo=timezone.utc)) is None


# --- Phase 3: ledger -----------------------------------------------------------------

def _doc(as_of, share, low=0.08, high=0.12):
    return {"as_of": as_of, "interval": {"model": "naive3"}, "nowcast": {"k": 0},
            "roles": {"backend_engineer": {"status": "ok", "share_now": {"value": share},
                                           "forecast_moderate": {"value_12m": 0.1, "low": low, "high": high},
                                           "trend": {"label": "Rising"}},
                      "mobile": {"status": "low_volume", "share_now": {"value": 0.01},
                                 "forecast_moderate": {"value_12m": None}, "trend": {"label": None}}}}


def test_ledger_records_one_row_per_role_and_day_and_reports_the_change(tmp_path):
    ledger.record(tmp_path, _doc("2026-11", 0.10), [], "2026-11-03", "2026-11")
    ledger.record(tmp_path, _doc("2026-11", 0.11), [], "2026-11-03", "2026-11")  # same day: replaced
    rows = ledger.record(tmp_path, _doc("2026-11", 0.12), [], "2026-11-04", "2026-11")
    assert [r["run_date"] for r in rows] == ["2026-11-03", "2026-11-04"]  # low_volume role not recorded
    s = ledger.summary(rows)
    assert s["runs"] == 2 and s["forecasts_graded"] == 0 and s["next_grading_month"] == "2027-11"
    assert s["changes_since_last_run"]["backend_engineer"] == {"since": "2026-11-03", "share_now_from": 0.11,
                                                               "share_now_to": 0.12}


def test_ledger_grades_a_forecast_once_its_target_month_is_complete(tmp_path):
    ledger.record(tmp_path, _doc("2026-11", 0.10), [], "2026-11-03", "2026-11")
    demand = [{"month": "2027-11", "role_id": "backend_engineer", "share": 0.115}]
    rows = ledger.record(tmp_path, _doc("2027-11", 0.11), demand, "2027-11-20", "2027-11")
    assert rows[0]["actual"] == ""  # 2027-11 is still open on 2027-11-20
    rows = ledger.record(tmp_path, _doc("2027-12", 0.11), demand, "2027-12-02", "2027-12")
    graded = [r for r in rows if r["as_of"] == "2026-11"]
    assert graded[0]["actual"] == "0.115000" and graded[0]["hit"] == "1"
    assert ledger.summary(rows)["forecasts_in_band"] == 1


# --- AI labeller: Claude first, checked quotes, regex backup -----------------------------

ROLES = [{"id": "backend_engineer", "name": "Backend Engineer", "description": "APIs.",
          "title_pattern": r"\bbackend engineer\b", "sdg": []},
         {"id": "data_engineer", "name": "Data Engineer", "description": "Pipelines.",
          "title_pattern": r"\bdata engineer\b", "sdg": []}]
IDS = {"backend_engineer", "data_engineer"}


def test_a_label_needs_a_quote_that_is_really_in_the_post():
    posts = {"1": "<p>Acme | Senior Backend Engineer | Remote</p>", "2": "We build pipelines", "3": "x"}
    text = json.dumps({"1": {"backend_engineer": "Senior Backend Engineer", "ceo": "Acme"},
                       "2": {"data_engineer": "Data Engineer wanted"},  # made-up quote: not in the post
                       "3": "data_engineer"})  # not an object
    labels, dropped = llm_labels.parse_answer("Sure! " + text, posts, IDS)
    assert labels == {"1": {"backend_engineer"}, "2": set()} and dropped == 1
    assert llm_labels.parse_answer("not json", posts, IDS) == ({}, 0)
    assert llm_labels.quote_ok("  backend   ENGINEER ", posts["1"]) and not llm_labels.quote_ok("ab", posts["1"])


def _thread(tmp_path, texts):
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    children = [{"id": i, "text": t} for i, t in enumerate(texts, 1)] + [{"id": 99, "deleted": True}]
    (raw / "9.json").write_text(json.dumps({"children": children}))
    return raw, {"thread_id": "9", "month": "2026-11"}


def test_claude_labels_first_and_the_regex_fills_in_without_caching(tmp_path):
    raw, thread = _thread(tmp_path, ["Acme | Backend Engineer", "Beta | Data Engineer", "Gamma | Data Engineer"])
    sent = []

    def fake(system, user):  # answers for posts 1 and 2 only; post 3 is missing from the answer
        sent.append(user)
        return json.dumps({"1": {"backend_engineer": "Backend Engineer"}, "2": {}})

    r = llm_labels.label_thread(tmp_path, raw, thread, ROLES, fake)
    assert r["labels"] == {"1": {"backend_engineer"}, "2": set(), "3": {"data_engineer"}}  # 3 from the regex
    assert (r["claude_posts"], r["regex_posts"], r["error"]) == (2, 1, None)
    assert r["disagree"] == 0.5  # post 2: Claude says none, the regex says data_engineer
    llm_labels.label_thread(tmp_path, raw, thread, ROLES, fake)
    assert 'id="1"' not in sent[1] and 'id="3"' in sent[1]  # cached post skipped, regex post asked again


def test_claude_down_means_regex_labels_and_no_failure(tmp_path):
    raw, thread = _thread(tmp_path, ["Acme | Backend Engineer"])

    def down(system, user):
        raise llm_labels.LabellerUnavailable("503")

    r = llm_labels.label_thread(tmp_path, raw, thread, ROLES, down)
    assert r["labels"] == {"1": {"backend_engineer"}} and r["claude_posts"] == 0 and "503" in r["error"]
    assert llm_labels.read_labels(tmp_path) == {}


def test_drift_check_compares_today_with_the_history_baseline():
    config = {"baseline_disagree": 0.12}
    assert llm_labels.drifted({"disagree": 0.30, "claude_posts": 50}, config)
    assert not llm_labels.drifted({"disagree": 0.20, "claude_posts": 50}, config)
    assert not llm_labels.drifted({"disagree": 0.90, "claude_posts": 5}, config)  # too few posts to judge
    assert not llm_labels.drifted({"disagree": 0.90, "claude_posts": 50}, {})  # no backfill yet


def test_claude_counts_only_after_the_backfill_switch(tmp_path):
    assert not llm_labels.uses_llm(tmp_path)
    (tmp_path / "role_labeller.json").write_text(json.dumps({"labeller": "llm", "baseline_disagree": 0.1}))
    assert llm_labels.uses_llm(tmp_path)


# --- Automatic new roles ------------------------------------------------------------------

def test_titles_drop_seniority_and_filler_words():
    text = "Acme | Senior Forward Deployed Engineer, Staff Research Engineers | hiring a great engineer"
    assert role_discover.titles(text) == {"forward deployed engineer", "research engineer"}


def test_candidates_catch_big_and_brand_new_titles_but_not_known_or_decided_ones():
    months = [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 13)]
    rows = [{"month": m, "title": "steady engineer", "posts": 3} for m in months]
    rows += [{"month": m, "title": "frontier modeler engineer", "posts": 6} for m in months[-3:]]
    rows += [{"month": m, "title": "backend engineer", "posts": 50} for m in months]
    rows += [{"month": m, "title": "noise engineer", "posts": 9} for m in months[-12:]]
    found = role_discover.candidates(rows, ROLES, {"noise engineer": {"decision": "noise"}})
    assert {c["title"]: c["why"] for c in found} == {"steady engineer": "big enough",
                                                     "frontier modeler engineer": "brand new"}


def test_a_new_role_needs_three_real_quotes_from_different_posts():
    ex = {"1": "Acme | Frontier Modeler Engineer", "2": "Beta hires a frontier modeler engineer",
          "3": "Gamma: Frontier Modeler Engineers wanted"}
    good = {"decision": "new_role", "name": "Frontier Modeler", "description": "Builds frontier models.",
            "quotes": ["Frontier Modeler Engineer", "a frontier modeler engineer", "Frontier Modeler Engineers wanted"]}
    title = "frontier modeler engineer"
    assert role_discover.check_review(good, title, ex, IDS) == "new_role"
    assert role_discover.check_review({**good, "quotes": ["Frontier Modeler Engineer"] * 3}, title, ex, IDS) is None
    made_up = {**good, "quotes": good["quotes"][:2] + ["Delta: frontier modeler engineer"]}
    assert role_discover.check_review(made_up, title, ex, IDS) is None
    assert role_discover.check_review({"decision": "existing", "existing_role_id": "ceo"}, title, ex, IDS) is None
    assert role_discover.check_review({"decision": "noise"}, title, ex, IDS) == "noise"


def test_daily_review_adds_a_checked_role_with_its_history(tmp_path):
    (tmp_path / "roles.json").write_text(json.dumps(ROLES))
    (tmp_path / "role_demand_monthly.csv").write_text(
        "month,role_id,mentions,n_posts,share\n"
        "2026-10,backend_engineer,5,100,0.050000\n2026-10,data_engineer,1,100,0.010000\n")
    (tmp_path / "title_counts_monthly.csv").write_text(
        "month,title,posts\n" + "".join(f"2026-{m:02d},frontier modeler engineer,{6 if m >= 9 else 0}\n"
                                        for m in range(1, 11)))
    raw, thread = _thread(tmp_path, [f"Co{i} | Frontier Modeler Engineer | Remote" for i in range(6)])

    def fake(system, user):
        return json.dumps({"decision": "new_role", "name": "Frontier Modeler Engineer",
                           "description": "Trains frontier models.", "reason": "A distinct job.",
                           "quotes": [f"Co{i} | Frontier Modeler Engineer" for i in range(3)]})

    doc = role_discover.daily(tmp_path, raw, thread, fake)
    assert doc["added"] == [{"id": "frontier_modeler_engineer", "name": "Frontier Modeler Engineer"}]
    role = json.loads((tmp_path / "roles.json").read_text())[-1]
    assert role["ranked"] is False and role["auto_added"]
    assert re.search(role["title_pattern"], "frontier-modeler engineers", re.I)
    assert "2026-10,frontier_modeler_engineer,6,100,0.060000" in (tmp_path / "role_demand_monthly.csv").read_text()
    assert role_discover.daily(tmp_path, raw, thread, lambda s, u: 1 / 0)["added"] == []  # decided: not asked again
