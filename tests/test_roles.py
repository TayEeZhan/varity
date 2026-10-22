"""Tests for engine.roles. Synthetic posts in tmp_path only; data/raw is never read."""
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import roles as R  # noqa: E402

SENTINEL = "ZZSECRET-PHRASE-7731 call jane.doe@example.test"

TAXONOMY = [
    {"skill": "Python", "pattern": r"\bpython\b", "case_sensitive": False},
    {"skill": "SQL", "pattern": r"\bsql\b", "case_sensitive": False},
    {"skill": "Airflow", "pattern": r"\bairflow\b", "case_sensitive": False},
    {"skill": "Docker", "pattern": r"\bdocker\b", "case_sensitive": False},
    {"skill": "Rust", "pattern": r"\brust\b", "case_sensitive": False},
]
ROLES = [
    {"id": "de", "name": "Data Engineer", "title_pattern": r"\bdata engineers?\b", "description": "d", "sdg": ["8.2"]},
    {"id": "sre", "name": "SRE", "title_pattern": r"\bsite reliability\b", "description": "s", "sdg": ["9.c"]},
]


# ---------------------------------------------------------------- helpers

def _post(text):
    return {"type": "comment", "text": text, "children": []}


def _month_list(n, start=(2024, 1)):
    y, m = start
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def write_corpus(tmp_path, posts_by_month):
    """posts_by_month: {"2024-01": [text, ...]}. Returns (raw_dir, threads_csv)."""
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    threads = tmp_path / "threads.csv"
    with threads.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["thread_id", "month", "created_at", "title", "url", "n_top_level"])
        for i, month in enumerate(sorted(posts_by_month), start=1):
            posts = posts_by_month[month]
            (raw / f"{i}.json").write_text(json.dumps({"children": [_post(t) for t in posts]}), encoding="utf-8")
            w.writerow([i, month, "x", "t", f"https://example.test/item?id={i}", len(posts)])
    return raw, threads


def spread(months, posts):
    """Round-robin the posts over the months."""
    out = {m: [] for m in months}
    for i, text in enumerate(posts):
        out[months[i % len(months)]].append(text)
    return out


def profile_corpus():
    """200 posts. 40 data-engineer posts, 160 others. Counts are exact, see the tests.

    Data-engineer posts (40): Python 30, SQL 20, Airflow 10, Docker 10, Rust 2.
    Other posts (160):        Python 16, SQL 20, Airflow 0,  Docker 80, Rust 40.
    All posts (200):          Python 46, SQL 40, Airflow 10, Docker 90, Rust 42.
    """
    posts = []
    for i in range(40):
        parts = ["Acme | Data Engineer"]
        if i < 30:
            parts.append("Python")
        if i < 20:
            parts.append("SQL")
        if i < 10:
            parts.append("Airflow")
            parts.append("Docker")
        if i in (38, 39):
            parts.append("Rust")
        posts.append(" | ".join(parts) + " " + SENTINEL)
    for i in range(160):
        parts = ["Beta | Office manager"]
        if i < 16:
            parts.append("Python")
        if i < 20:
            parts.append("SQL")
        if i < 80:
            parts.append("Docker")
        if i < 40:
            parts.append("Rust")
        posts.append(" | ".join(parts))
    return posts


@pytest.fixture
def learned(tmp_path):
    months = _month_list(4)
    raw, threads = write_corpus(tmp_path, spread(months, profile_corpus()))
    doc = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES, months=24)
    return doc, {r["role_id"]: r for r in doc["roles"]}


# ---------------------------------------------------------------- roles.json and title patterns

@pytest.fixture(scope="module")
def real_roles():
    return R.load_roles()


@pytest.fixture(scope="module")
def real_patterns(real_roles):
    return R.compile_patterns(real_roles)


def roles_for(text, patterns):
    return R.matching_roles(text, patterns)


def test_roles_json_has_the_eight_roles(real_roles):
    assert [r["name"] for r in real_roles] == [
        "Data Engineer", "Analytics Engineer", "ML Engineer", "AI/LLM Application Engineer",
        "Backend Engineer", "Full-stack Web Developer", "Platform/DevOps Engineer", "Mobile Developer",
    ]
    assert len({r["id"] for r in real_roles}) == 8


def test_roles_json_sdg_codes_come_from_the_taxonomy(real_roles):
    taxonomy = json.loads((ROOT / "data" / "taxonomy.json").read_text(encoding="utf-8"))
    known = {code for entry in taxonomy for code in entry["sdg"]}
    for role in real_roles:
        assert 1 <= len(role["sdg"]) <= 2
        assert set(role["sdg"]) <= known, role["id"]
        assert role["sdg_reason"].strip()
        assert "%" not in role["sdg_reason"], "no statistics in sdg_reason"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Acme | Senior Data Engineer | Remote", {"data_engineer"}),
        ("We are hiring data engineers to build pipelines", {"data_engineer"}),
        ("Lead our Data Engineering team", {"data_engineer"}),
        ("Analytics Engineer (dbt, Snowflake)", {"analytics_engineer"}),
        ("Staff Machine Learning Engineer", {"ml_engineer"}),
        ("Machine-Learning Engineer, ranking", {"ml_engineer"}),
        ("ML Engineer", {"ml_engineer"}),
        ("AI/ML Engineer", {"ml_engineer"}),
        ("ML/AI Engineer", {"ml_engineer"}),
        ("MLOps Engineer", {"ml_engineer"}),
        ("AI Engineer", {"ai_app_engineer"}),
        ("Applied AI Engineer", {"ai_app_engineer"}),
        ("LLM engineer wanted", {"ai_app_engineer"}),
        ("GenAI Engineer", {"ai_app_engineer"}),
        ("Gen AI developer", {"ai_app_engineer"}),
        ("Generative AI Engineer", {"ai_app_engineer"}),
        ("AI Application Engineer", {"ai_app_engineer"}),
        ("Backend Engineer", {"backend_engineer"}),
        ("Back-end developers", {"backend_engineer"}),
        ("Senior Backend Software Engineer", {"backend_engineer"}),
        ("Full-Stack Developer", {"fullstack_developer"}),
        ("Fullstack engineer", {"fullstack_developer"}),
        ("Full Stack Web Developer", {"fullstack_developer"}),
        ("DevOps Engineer", {"platform_devops_engineer"}),
        ("Site Reliability Engineer", {"platform_devops_engineer"}),
        ("SRE / on-call", {"platform_devops_engineer"}),
        ("Platform Engineer", {"platform_devops_engineer"}),
        ("iOS Developer", {"mobile_developer"}),
        ("Android engineer", {"mobile_developer"}),
        ("Mobile App Developer", {"mobile_developer"}),
        ("React Native Developer", {"mobile_developer"}),
        ("Data Engineer and Analytics Engineer", {"data_engineer", "analytics_engineer"}),
    ],
)
def test_title_patterns_positive(text, expected, real_patterns):
    assert roles_for(text, real_patterns) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Software Engineer",
        "We are an AI company hiring engineers",
        "AI startup looking for a designer",
        "Data Scientist",
        "Data Analyst",
        "We use data to engineer better products",
        "Big data and engineer-friendly culture",
        "XML engineer",
        "HTML engineer",
        "Frontend Engineer (React)",
        "Python backend experience helps",
        "Our team practices DevOps and CI",
        "Mobile phone engineer",
        "Rail engineer",
        "Sales engineer",
    ],
)
def test_title_patterns_negative(text, real_patterns):
    assert roles_for(text, real_patterns) == set()


@pytest.mark.parametrize("text", ["Machine Learning Engineer", "ML engineer", "AI/ML Engineer", "ML/AI Engineer",
                                  "MLOps Engineer"])
def test_ml_engineer_is_not_counted_as_ai_engineer(text, real_patterns):
    assert "ai_app_engineer" not in roles_for(text, real_patterns)


def test_data_engineer_and_analytics_engineer_do_not_overlap(real_patterns):
    assert "analytics_engineer" not in roles_for("Data Engineer", real_patterns)
    assert "data_engineer" not in roles_for("Analytics Engineer", real_patterns)


def test_patterns_clean_html_first(real_patterns):
    assert roles_for("Acme | Data&nbsp;Engineer<p>Remote", real_patterns) == {"data_engineer"}  # nbsp is a space
    assert roles_for("Acme | <b>Data Engineer</b><p>Remote", real_patterns) == {"data_engineer"}
    assert roles_for("", real_patterns) == set()


def test_load_roles_rejects_bad_files(tmp_path):
    bad = tmp_path / "roles.json"
    bad.write_text(json.dumps([{"id": "x", "name": "X"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        R.load_roles(bad)
    dup = [dict(ROLES[0]), dict(ROLES[0])]
    bad.write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        R.load_roles(bad)


# ---------------------------------------------------------------- learned weights

def test_learned_counts_and_filters(learned):
    doc, by_id = learned
    assert doc["n_posts_all"] == 200
    de = by_id["de"]
    assert de["n_role_posts"] == 40
    skills = {s["skill"]: s for s in de["skills"]}
    # Kept: Python, SQL, Airflow. Docker fails lift (0.25 / 0.45). Rust fails p_role (2/40 = 0.05).
    assert set(skills) == {"Python", "SQL", "Airflow"}
    assert skills["Python"]["p_role"] == pytest.approx(30 / 40)
    assert skills["Python"]["p_all"] == pytest.approx(46 / 200)
    assert skills["Python"]["lift"] == pytest.approx((30 / 40) / (46 / 200), abs=1e-3)
    assert skills["Airflow"]["lift"] == pytest.approx((10 / 40) / (10 / 200), abs=1e-3)


def test_docker_dropped_for_low_lift_and_rust_for_low_p_role(learned):
    _, by_id = learned
    names = {s["skill"] for s in by_id["de"]["skills"]}
    assert "Docker" not in names  # lift 0.55 < 1.2
    assert "Rust" not in names  # p_role 0.05 < 0.08


def test_weights_are_p_role_normalised_to_one_and_sorted(learned):
    _, by_id = learned
    skills = by_id["de"]["skills"]
    assert sum(s["weight"] for s in skills) == pytest.approx(1.0, abs=1e-5)
    total = 30 / 40 + 20 / 40 + 10 / 40
    assert skills[0]["skill"] == "Python"
    assert skills[0]["weight"] == pytest.approx((30 / 40) / total, abs=1e-5)
    assert [s["skill"] for s in skills] == ["Python", "SQL", "Airflow"]
    assert [s["weight"] for s in skills] == sorted((s["weight"] for s in skills), reverse=True)


def test_threshold_is_inclusive_at_exactly_eight_percent(tmp_path):
    # 3 of 50 role posts (6%) fails; 4 of 50 (8%) passes. The skill is rare elsewhere so lift is high.
    posts = []
    for i in range(50):
        posts.append("Data Engineer | " + ("SQL" if i < 4 else "") + (" Rust" if i < 3 else ""))
    posts += ["Other job"] * 50
    raw, threads = write_corpus(tmp_path, spread(_month_list(2), posts))
    doc = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES)
    names = {s["skill"] for s in doc["roles"][0]["skills"]}
    assert "SQL" in names and "Rust" not in names


def test_lift_filter_is_inclusive_at_1_2(tmp_path):
    # Role posts: 50, 24 mention SQL (p_role 0.48). Others: 50. Skill in 'others' set so p_all = 0.4
    # -> lift 1.2 exactly passes. With p_all = 0.41 it would fail.
    posts = ["Data Engineer | SQL"] * 24 + ["Data Engineer"] * 26
    posts += ["Misc | SQL"] * 16 + ["Misc"] * 34  # p_all = 40/100 = 0.4
    raw, threads = write_corpus(tmp_path, spread(_month_list(2), posts))
    doc = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES)
    skills = {s["skill"]: s for s in doc["roles"][0]["skills"]}
    assert skills["SQL"]["lift"] == pytest.approx(1.2)


def test_only_top_ten_skills_are_kept(tmp_path):
    taxonomy = [{"skill": f"S{i:02d}", "pattern": rf"\bs{i:02d}\b", "case_sensitive": False} for i in range(12)]
    posts = []
    for i in range(40):  # skill k appears in 40 - k posts: S00 40 ... S11 29 of 40 role posts
        posts.append("Data Engineer " + " ".join(f"S{k:02d}" for k in range(12) if i < 40 - k))
    posts += ["Other"] * 200  # so lift is high for every skill
    raw, threads = write_corpus(tmp_path, spread(_month_list(2), posts))
    doc = R.learn_role_profiles(raw, threads, taxonomy, ROLES)
    skills = doc["roles"][0]["skills"]
    assert [s["skill"] for s in skills] == [f"S{i:02d}" for i in range(10)]
    assert sum(s["weight"] for s in skills) == pytest.approx(1.0, abs=1e-5)


def test_window_uses_last_months_and_as_of(tmp_path):
    months = _month_list(6)
    by_month = {m: ["Other job"] * 5 for m in months}
    by_month["2024-01"] = ["Data Engineer | Python"] * 3 + ["Other job"] * 2  # old posts
    by_month["2024-06"] = ["Data Engineer | SQL"] * 2 + ["Other job"] * 3
    raw, threads = write_corpus(tmp_path, by_month)

    full = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES, months=24)
    assert full["roles"][0]["n_role_posts"] == 5
    assert full["window"] == {"from": "2024-01", "to": "2024-06", "months": 6}

    recent = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES, months=3)
    assert recent["roles"][0]["n_role_posts"] == 2
    assert recent["window"]["from"] == "2024-04"

    earlier = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES, months=3, as_of="2024-04")
    assert earlier["roles"][0]["n_role_posts"] == 0  # 2024-02..2024-04: the old and new posts are both outside
    assert earlier["window"]["to"] == "2024-04"
    assert earlier["roles"][0]["skills"] == []
    assert earlier["as_of"] == "2024-04"


def test_months_must_be_positive(tmp_path):
    raw, threads = write_corpus(tmp_path, {"2024-01": ["x"]})
    with pytest.raises(ValueError):
        R.learn_role_profiles(raw, threads, TAXONOMY, ROLES, months=0)


def test_deleted_and_empty_posts_are_not_counted(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    item = {"children": [
        _post("Data Engineer | Python"),
        {"deleted": True, "text": "Data Engineer | Python"},
        _post("   "),
        {"type": "comment", "children": []},
    ]}
    (raw / "1.json").write_text(json.dumps(item), encoding="utf-8")
    threads = tmp_path / "threads.csv"
    threads.write_text("thread_id,month,created_at,title,url,n_top_level\n1,2024-01,x,t,u,4\n", encoding="utf-8")
    doc = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES)
    assert doc["n_posts_all"] == 1
    assert doc["roles"][0]["n_role_posts"] == 1


def test_a_post_counts_once_per_role_and_can_match_two_roles(tmp_path):
    posts = ["Data Engineer, data engineers, DATA ENGINEER | site reliability | Python Python"]
    raw, threads = write_corpus(tmp_path, {"2024-01": posts})
    doc = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES)
    counts = {r["role_id"]: r["n_role_posts"] for r in doc["roles"]}
    assert counts == {"de": 1, "sre": 1}


def test_thin_profile_flag(tmp_path):
    posts = ["Data Engineer | Python"] * 29 + ["site reliability | Python"] * 30 + ["Other"] * 60
    raw, threads = write_corpus(tmp_path, spread(_month_list(2), posts))
    doc = R.learn_role_profiles(raw, threads, TAXONOMY, ROLES)
    by_id = {r["role_id"]: r for r in doc["roles"]}
    assert by_id["de"]["n_role_posts"] == 29
    assert by_id["de"]["profile_status"] == "thin"
    assert "thin" in by_id["de"]["note"].lower() and "29" in by_id["de"]["note"]
    assert by_id["sre"]["n_role_posts"] == 30
    assert by_id["sre"]["profile_status"] == "ok"
    assert by_id["sre"]["note"] is None


def test_profile_lists_the_threads_used(learned):
    doc, by_id = learned
    assert doc["thread_ids"] == ["1", "2", "3", "4"]
    assert set(by_id["de"]["thread_ids"]) <= set(doc["thread_ids"])
    assert by_id["sre"]["thread_ids"] == []


# ---------------------------------------------------------------- role demand and trends

def test_role_demand_counts_and_csv(tmp_path):
    by_month = {
        "2024-01": ["Data Engineer | Python", "Data engineers wanted", "Other", "site reliability and data engineer"],
        "2024-02": ["Other"] * 3,
    }
    raw, threads = write_corpus(tmp_path, by_month)
    out = tmp_path / "out" / "role_demand.csv"
    rows = R.role_demand(raw, threads, ROLES, out_csv=out)
    got = {(r["month"], r["role_id"]): (r["mentions"], r["n_posts"]) for r in rows}
    assert got == {
        ("2024-01", "de"): (3, 4), ("2024-01", "sre"): (1, 4),
        ("2024-02", "de"): (0, 3), ("2024-02", "sre"): (0, 3),
    }
    assert rows[0]["share"] == pytest.approx(0.75)
    with out.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["month", "role_id", "mentions", "n_posts", "share"]
        first = next(reader)
    assert first == {"month": "2024-01", "role_id": "de", "mentions": "3", "n_posts": "4", "share": "0.750000"}


def _demand_rows(role_id, prev, recent, n_posts=300, months=24):
    """24 months: first 12 have `prev` mentions each, last 12 have `recent`."""
    ms = _month_list(months)
    return [{"month": m, "role_id": role_id, "mentions": prev if i < months - 12 else recent,
             "n_posts": n_posts, "share": 0.0} for i, m in enumerate(ms)]


def test_role_trends_use_the_skill_welch_rule():
    # Same numbers through the skill function give the same label.
    from engine.forecast import logit, smoothed_share, trend_label

    rows = (_demand_rows("up", 10, 25) + _demand_rows("down", 25, 10) + _demand_rows("flat", 15, 15)
            + _demand_rows("rare", 1, 1))
    roles = [{"id": r} for r in ("up", "down", "flat", "rare")]
    doc = R.build_role_trends(rows, roles, today=datetime(2030, 1, 1, tzinfo=timezone.utc))
    labels = {k: v["trend_label"] for k, v in doc["roles"].items()}
    assert labels == {"up": "Rising", "down": "Falling", "flat": "No clear change", "rare": None}
    up = doc["roles"]["up"]
    assert (up["mentions_last12"], up["mentions_prev12"]) == (300, 120)
    assert (up["posts_last12"], up["posts_prev12"]) == (3600, 3600)
    assert doc["roles"]["rare"]["trend_p"] is None  # 24 mentions < 30
    y = logit(smoothed_share([10] * 12 + [25] * 12, [300] * 24))
    assert trend_label(y, [10] * 12 + [25] * 12)[0] == "Rising"
    assert doc["as_of"] == "2025-12"
    assert doc["partial_month"] is False


def test_role_trend_needs_24_months_and_30_mentions():
    short = _demand_rows("r", 10, 30, months=23)
    doc = R.build_role_trends(short, [{"id": "r"}])
    assert doc["roles"]["r"]["trend_label"] is None
    exact = _demand_rows("r", 1, 1)  # 24 mentions in total
    assert R.build_role_trends(exact, [{"id": "r"}])["roles"]["r"]["trend_label"] is None
    enough = _demand_rows("r", 1, 2)  # 36 mentions in total
    assert R.build_role_trends(enough, [{"id": "r"}])["roles"]["r"]["trend_label"] is not None


def test_role_trend_as_of_cuts_the_future():
    rows = _demand_rows("r", 10, 25, months=26)  # 2024-01 .. 2026-02
    full = R.build_role_trends(rows, [{"id": "r"}])
    cut = R.build_role_trends(rows, [{"id": "r"}], as_of="2025-12")
    assert full["as_of"] == "2026-02" and cut["as_of"] == "2025-12"
    assert cut["roles"]["r"]["mentions_last12"] == 2 * 10 + 10 * 25  # months 2025-01..2025-12


def test_partial_month_flag():
    rows = _demand_rows("r", 10, 10)
    assert R.build_role_trends(rows, [{"id": "r"}], today=datetime(2025, 12, 5, tzinfo=timezone.utc))["partial_month"]


# ---------------------------------------------------------------- match

def _profiles(*roles):
    return {"roles": list(roles)}


def _role(role_id, name, skills, status="ok", n=100):
    return {"role_id": role_id, "name": name, "description": "d", "sdg": ["8.2"], "profile_status": status,
            "n_role_posts": n, "skills": [{"skill": s, "weight": w} for s, w in skills]}


def _scores(**stances):
    """skill -> (stance, status, trend). Only the fields match_roles reads."""
    return {"skills": [{"skill": s, "stance": st, "status": status, "trend_label": tr}
                       for s, (st, status, tr) in stances.items()]}


def _trends(**roles):
    return {"roles": {rid: {"trend_label": label, "trend_p": 0.01, "mentions_last12": a, "mentions_prev12": b}
                      for rid, (label, a, b) in roles.items()}}


SCORES = _scores(
    Python=("AI-substitutable", "ok", "No clear change"),
    SQL=("neutral", "ok", "No clear change"),
    Airflow=("neutral", "low_volume", "Rising"),
    dbt=("neutral", "low_volume", "Rising"),
    LLM=("AI-complement", "ok", "No clear change"),
    RAG=("AI-complement", "ok", "Rising"),
)
DE = _role("de", "Data Engineer", [("Python", 0.4), ("SQL", 0.3), ("Airflow", 0.2), ("dbt", 0.1)])


def test_match_score_is_weight_of_owned_skills_over_total():
    out = R.match_roles({"Python", "SQL"}, _profiles(DE), SCORES, _trends(de=("Rising", 182, 140)))
    role = out["roles"][0]
    assert role["match_score"] == pytest.approx(0.7)
    assert [s["skill"] for s in role["have"]] == ["Python", "SQL"]


def test_match_score_normalises_weights_that_do_not_sum_to_one():
    prof = _role("de", "Data Engineer", [("Python", 2), ("SQL", 1), ("Airflow", 1)])
    out = R.match_roles({"Python"}, _profiles(prof), SCORES, {})
    assert out["roles"][0]["match_score"] == pytest.approx(0.5)


def test_match_score_extremes_and_empty_profile():
    none = R.match_roles(set(), _profiles(DE), SCORES, {})["roles"][0]
    assert none["match_score"] == 0.0 and none["have"] == []
    all_ = R.match_roles({"Python", "SQL", "Airflow", "dbt"}, _profiles(DE), SCORES, {})["roles"][0]
    assert all_["match_score"] == pytest.approx(1.0) and all_["gap"] == []
    empty = R.match_roles({"Python"}, _profiles(_role("x", "X", [], status="thin", n=3)), SCORES, {})["roles"][0]
    assert empty["match_score"] == 0.0
    assert "No skill profile" in empty["reason"]


def test_skills_the_roles_do_not_use_are_ignored():
    out = R.match_roles({"Python", "Cobol"}, _profiles(DE), SCORES, {})["roles"][0]
    assert out["match_score"] == pytest.approx(0.4)


def test_user_skills_as_dict_keeps_years():
    out = R.match_roles({"Python": 3, "SQL": 1.5}, _profiles(DE), SCORES, {})["roles"][0]
    assert {s["skill"]: s["years"] for s in out["have"]} == {"Python": 3, "SQL": 1.5}


def test_gap_is_ordered_by_weight_and_carries_skill_facts():
    prof = _role("de", "Data Engineer", [("dbt", 0.1), ("Airflow", 0.2), ("SQL", 0.3), ("Python", 0.4)])
    gap = R.match_roles({"SQL"}, _profiles(prof), SCORES, {})["roles"][0]["gap"]
    assert [g["skill"] for g in gap] == ["Python", "Airflow", "dbt"]
    assert gap[0] == {"skill": "Python", "weight": 0.4, "status": "ok", "trend_label": "No clear change",
                      "stance": "AI-substitutable"}
    assert gap[1]["status"] == "low_volume" and gap[1]["trend_label"] == "Rising"


def test_gap_skill_missing_from_skill_scores_has_none_fields():
    prof = _role("x", "X", [("Mystery", 1.0)])
    gap = R.match_roles(set(), _profiles(prof), SCORES, {})["roles"][0]["gap"]
    assert gap == [{"skill": "Mystery", "weight": 1.0, "status": None, "trend_label": None, "stance": None}]


def test_equal_weights_break_ties_by_name():
    prof = _role("x", "X", [("SQL", 0.5), ("Airflow", 0.5)])
    gap = R.match_roles(set(), _profiles(prof), SCORES, {})["roles"][0]["gap"]
    assert [g["skill"] for g in gap] == ["Airflow", "SQL"]


@pytest.mark.parametrize(
    "label, expected",
    [("Rising", 1.0), ("No clear change", 0.5), ("Falling", 0.0), (None, 0.5)],
)
def test_future_score_from_trend(label, expected):
    out = R.match_roles({"Python"}, _profiles(DE), SCORES, _trends(de=(label, 10, 10)))
    role = out["roles"][0]
    assert role["future_score"] == expected
    assert role["scenario_adjustment"] == 0.0
    assert role["rank_score"] == pytest.approx(0.7 * 0.4 + 0.3 * expected)


def test_missing_trend_entry_counts_as_unknown():
    role = R.match_roles({"Python"}, _profiles(DE), SCORES, {})["roles"][0]
    assert role["future_score"] == 0.5
    assert role["outlook"]["trend_label"] is None


def test_fast_scenario_adjusts_for_ai_stance_but_moderate_does_not():
    ai = _role("ai", "AI", [("LLM", 0.4), ("RAG", 0.3), ("SQL", 0.3)])  # 70% complement
    sub = _role("sub", "Sub", [("Python", 0.6), ("SQL", 0.4)])  # 60% substitutable
    mixed = _role("mix", "Mix", [("Python", 0.5), ("LLM", 0.5)])  # 50 / 50: no adjustment
    trends = _trends(ai=("No clear change", 1, 1), sub=("No clear change", 1, 1), mix=("No clear change", 1, 1))
    prof = _profiles(ai, sub, mixed)
    moderate = {r["role_id"]: r for r in R.match_roles(set(), prof, SCORES, trends, "moderate")["roles"]}
    fast = {r["role_id"]: r for r in R.match_roles(set(), prof, SCORES, trends, "fast")["roles"]}
    assert {k: v["future_score"] for k, v in moderate.items()} == {"ai": 0.5, "sub": 0.5, "mix": 0.5}
    assert fast["ai"]["future_score"] == pytest.approx(0.6)
    assert fast["sub"]["future_score"] == pytest.approx(0.4)
    assert fast["mix"]["future_score"] == pytest.approx(0.5)
    assert fast["ai"]["scenario_adjustment"] == 0.1 and fast["sub"]["scenario_adjustment"] == -0.1
    assert fast["ai"]["ai_stance_weights"]["AI-complement"] == pytest.approx(0.7)


def test_fast_scenario_is_clipped_to_unit_interval():
    ai = _role("ai", "AI", [("LLM", 1.0)])
    sub = _role("sub", "Sub", [("Python", 1.0)])
    trends = _trends(ai=("Rising", 1, 1), sub=("Falling", 1, 1))
    fast = {r["role_id"]: r for r in R.match_roles(set(), _profiles(ai, sub), SCORES, trends, "fast")["roles"]}
    assert fast["ai"]["future_score"] == 1.0
    assert fast["sub"]["future_score"] == 0.0


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="scenario"):
        R.match_roles(set(), _profiles(DE), SCORES, {}, "slow")


def test_ranking_order_and_rank_numbers():
    a = _role("a", "Alpha", [("Python", 1.0)])
    b = _role("b", "Beta", [("SQL", 1.0)])
    c = _role("c", "Gamma", [("Airflow", 1.0)])
    trends = _trends(a=("Falling", 1, 1), b=("Rising", 1, 1), c=("Rising", 1, 1))
    out = R.match_roles({"Python"}, _profiles(a, b, c), SCORES, trends)
    # Alpha: 0.7 * 1 + 0 = 0.70. Beta and Gamma: 0 + 0.3 = 0.30 (tie: name order).
    assert [r["name"] for r in out["roles"]] == ["Alpha", "Beta", "Gamma"]
    assert [r["rank"] for r in out["roles"]] == [1, 2, 3]
    assert out["roles"][0]["rank_score"] == pytest.approx(0.7)
    assert out["roles"][1]["rank_score"] == pytest.approx(0.3)


def test_future_can_outrank_a_small_match_advantage():
    hi = _role("hi", "Hi", [("Python", 0.5), ("SQL", 0.5)])  # match 0.5, Falling -> 0.35
    lo = _role("lo", "Lo", [("Python", 0.4), ("SQL", 0.6)])  # match 0.4, Rising -> 0.58
    out = R.match_roles({"Python"}, _profiles(hi, lo), SCORES, _trends(hi=("Falling", 1, 1), lo=("Rising", 1, 1)))
    assert [r["role_id"] for r in out["roles"]] == ["lo", "hi"]


def test_output_states_the_team_judgement_constants():
    out = R.match_roles(set(), _profiles(DE), SCORES, {})
    f = out["formula"]
    assert (f["match_weight"], f["future_weight"], f["fast_adjustment"]) == (0.7, 0.3, 0.1)
    assert "team judgement" in f["basis"]
    assert out["scenario"] == "moderate"


def test_reason_string():
    out = R.match_roles({"Python", "SQL"}, _profiles(DE), SCORES, _trends(de=("Rising", 182, 140)))
    assert out["roles"][0]["reason"] == (
        "You have 2 of its top 4 skills (Python, SQL). Biggest gaps: Airflow, dbt. "
        "Role demand: Rising (182 vs 140 posts)."
    )


def test_reason_for_no_overlap_no_gap_no_trend_and_thin():
    none = R.match_roles(set(), _profiles(DE), SCORES, {})["roles"][0]["reason"]
    assert none.startswith("You have none of its top 4 skills.")
    assert "Role demand: too few posts to label a trend." in none
    full = R.match_roles({"Python", "SQL", "Airflow", "dbt"}, _profiles(DE), SCORES, {})["roles"][0]["reason"]
    assert "No gaps among its top skills." in full
    thin = _role("t", "T", [("Python", 1.0)], status="thin", n=12)
    reason = R.match_roles({"Python"}, _profiles(thin), SCORES, {})["roles"][0]["reason"]
    assert reason.endswith("Thin profile: built from only 12 posts.")


def test_reason_shows_at_most_four_skills_and_three_gaps():
    prof = _role("x", "X", [(f"S{i}", 1 - i * 0.05) for i in range(10)])
    reason = R.match_roles({f"S{i}" for i in range(5)}, _profiles(prof), SCORES, {})["roles"][0]["reason"]
    assert "You have 5 of its top 10 skills (S0, S1, S2, S3)." in reason
    assert "Biggest gaps: S5, S6, S7." in reason


def test_accepts_bare_lists_and_mappings():
    out = R.match_roles({"Python"}, [DE], SCORES["skills"], _trends(de=("Rising", 2, 1))["roles"])
    assert out["roles"][0]["outlook"]["trend_label"] == "Rising"


def test_demo_users_through_real_files_if_present():
    files = [ROOT / "data" / n for n in ("role_profiles.json", "role_trends.json", "skill_scores.json")]
    if not all(f.exists() for f in files):
        pytest.skip("generated files not built yet")
    profiles, trends, scores = (json.loads(f.read_text(encoding="utf-8")) for f in files)
    out = R.match_roles({"Python", "SQL", "PostgreSQL", "Docker", "AWS"}, profiles, scores, trends)
    assert len(out["roles"]) == 8
    ranks = [r["rank_score"] for r in out["roles"]]
    assert ranks == sorted(ranks, reverse=True)
    assert all(0.0 <= r["rank_score"] <= 1.0 for r in out["roles"])


# ---------------------------------------------------------------- committed output files

def test_committed_profiles_are_consistent_if_present():
    path = ROOT / "data" / "role_profiles.json"
    if not path.exists():
        pytest.skip("role_profiles.json not built yet")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for role in doc["roles"]:
        assert role["profile_status"] == ("thin" if role["n_role_posts"] < 30 else "ok")
        assert len(role["skills"]) <= 10
        if role["skills"]:
            assert sum(s["weight"] for s in role["skills"]) == pytest.approx(1.0, abs=1e-4)
        for s in role["skills"]:
            assert s["p_role"] >= 0.08 - 1e-9 and s["lift"] >= 1.2 - 1e-3


# ---------------------------------------------------------------- privacy and main

def test_no_post_text_reaches_any_output_file(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("taxonomy.json", "roles.json"):
        shutil.copy(ROOT / "data" / name, data_dir / name)
    months = _month_list(26)
    posts = [f"Acme | Data Engineer | Python SQL | {SENTINEL}", f"Beta | ML Engineer | {SENTINEL}",
             "Gamma | Backend Engineer | Go", "Plain post"] * 3
    raw, threads = write_corpus(tmp_path, {m: list(posts) for m in months})
    assert R.main(["--raw-dir", str(raw), "--threads-csv", str(threads), "--data-dir", str(data_dir)]) == 0

    written = [data_dir / n for n in ("role_profiles.json", "role_demand_monthly.csv", "role_trends.json")]
    assert all(p.exists() for p in written)
    for path in written:
        content = path.read_text(encoding="utf-8")
        assert "ZZSECRET" not in content and "jane.doe" not in content and "example.test" not in content, path.name
        assert "Acme" not in content and "Gamma" not in content and "Plain post" not in content, path.name
    profiles = json.loads(written[0].read_text(encoding="utf-8"))
    allowed = {"role_id", "name", "description", "sdg", "n_role_posts", "window", "profile_status", "note",
               "skills", "thread_ids"}
    assert all(set(r) == allowed for r in profiles["roles"])
    assert all(set(s) == {"skill", "weight", "p_role", "p_all", "lift"} for r in profiles["roles"] for s in r["skills"])
    de = next(r for r in profiles["roles"] if r["role_id"] == "data_engineer")
    assert de["n_role_posts"] == 3 * 24 and de["profile_status"] == "ok"
    trends = json.loads(written[2].read_text(encoding="utf-8"))
    assert trends["roles"]["data_engineer"]["trend_label"] == "No clear change"
