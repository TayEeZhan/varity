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
from engine.tagging import load_taxonomy, tag_text  # noqa: E402

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
DATA = ROOT / "data"
PERSONAS = {
    "Aina": {"Python", "SQL", "PostgreSQL", "Docker", "AWS"},
    "Ben": {"JavaScript / TypeScript", "TypeScript", "React", "Node.js"},
    "Chloe": {"SQL", "Python", "Snowflake", "dbt"},
}


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
    """200 posts. 40 data-engineer posts (all single-role), 160 others. Counts are exact.

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


def learn(tmp_path, posts_by_month, taxonomy=TAXONOMY, roles=ROLES, **kw):
    raw, threads = write_corpus(tmp_path, posts_by_month)
    return R.learn_role_profiles(raw, threads, taxonomy, roles, **kw)


@pytest.fixture
def learned(tmp_path):
    doc = learn(tmp_path, spread(_month_list(4), profile_corpus()))
    return doc, {r["role_id"]: r for r in doc["roles"]}


# ---------------------------------------------------------------- roles.json and title patterns

@pytest.fixture(scope="module")
def real_roles():
    return R.load_roles()


@pytest.fixture(scope="module")
def real_patterns(real_roles):
    return R.compile_patterns(real_roles)


@pytest.fixture(scope="module")
def real_taxonomy():
    return load_taxonomy()


def roles_for(text, patterns):
    return R.matching_roles(text, patterns)


def test_roles_json_has_nine_roles_and_eight_are_ranked(real_roles):
    assert [r["name"] for r in real_roles] == [
        "Data Engineer", "Analytics Engineer", "Data Scientist", "ML Engineer", "AI/LLM Application Engineer",
        "Backend Engineer", "Full-stack Web Developer", "Platform/DevOps Engineer", "Mobile Developer",
    ]
    assert len({r["id"] for r in real_roles}) == 9
    unranked = [r for r in real_roles if r.get("ranked") is False]
    assert [r["id"] for r in unranked] == ["analytics_engineer"]
    assert unranked[0]["note"] == "Not ranked: too few posts to learn a profile"
    assert sum(1 for r in real_roles if r.get("ranked", True)) == 8


def test_roles_json_sdg_codes_come_from_the_taxonomy(real_roles):
    taxonomy = json.loads((DATA / "taxonomy.json").read_text(encoding="utf-8"))
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
        ("Data Scientist", {"data_scientist"}),
        ("We need data scientists", {"data_scientist"}),
        ("Senior Data-Scientist", {"data_scientist"}),
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
        "Data Analyst",
        "We use data to engineer better products",
        "Big data and engineer-friendly culture",
        "Science data and engineers",
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


# ---------------------------------------------------------------- title masking

def test_mask_spans_blanks_the_span_and_keeps_length():
    text = "Acme | Data Engineer | Python"
    masked = R.mask_spans(text, [(7, 20)])
    assert masked == "Acme | " + " " * 13 + " | Python"
    assert len(masked) == len(text)


def test_title_does_not_create_its_own_skill(real_patterns, real_taxonomy):
    # Without masking, the titles "LLM engineer" and "ML engineer" tag LLM / GenAI and Machine Learning.
    for title, skill, role in (("LLM Engineer", "LLM / GenAI", "ai_app_engineer"),
                               ("ML Engineer", "Machine Learning", "ml_engineer")):
        text = f"Acme | {title} | Remote | Python"
        assert skill in tag_text(text, real_taxonomy)
        rids, skills = R.tag_role_post(text, real_patterns, real_taxonomy)
        assert rids == {role}
        assert skill not in skills
        assert "Python" in skills  # the rest of the post is still tagged


def test_a_real_skill_next_to_the_title_survives_masking(real_patterns, real_taxonomy):
    rids, skills = R.tag_role_post("Machine Learning Engineer | PyTorch, machine learning research",
                                   real_patterns, real_taxonomy)
    assert rids == {"ml_engineer"}
    assert "PyTorch" in skills and "Machine Learning" in skills  # 'machine learning research' is outside the title


def test_masked_title_skill_is_not_counted_in_profiles(tmp_path):
    taxonomy = TAXONOMY + [{"skill": "Pipelines", "pattern": r"\bdata engineer", "case_sensitive": False}]
    posts = ["Acme | Data Engineer | Python"] * 20 + ["Other"] * 20
    doc = learn(tmp_path, spread(_month_list(2), posts), taxonomy=taxonomy)
    names = {s["skill"] for s in doc["roles"][0]["skills"]}
    assert "Python" in names and "Pipelines" not in names  # the title would have created 'Pipelines'


# ---------------------------------------------------------------- learned weights

def test_learned_counts_and_filters(learned):
    doc, by_id = learned
    assert doc["n_posts_all"] == 200
    de = by_id["de"]
    assert (de["n_role_posts"], de["n_single_role_posts"]) == (40, 40)
    skills = {s["skill"]: s for s in de["skills"]}
    # Kept: Python, SQL, Airflow. Docker fails lift (0.25 / 0.45). Rust fails p_role (2/40 = 0.05).
    assert set(skills) == {"Python", "SQL", "Airflow"}
    assert skills["Python"]["p_role"] == pytest.approx(30 / 40)
    assert skills["Python"]["p_all"] == pytest.approx(46 / 200)
    assert skills["Python"]["lift"] == pytest.approx((30 / 40) / (46 / 200), abs=1e-3)
    assert skills["Airflow"]["lift"] == pytest.approx((10 / 40) / (10 / 200), abs=1e-3)
    assert skills["Airflow"]["single_role_posts"] == 10


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
    assert skills[0]["weight"] == pytest.approx((30 / 40) / total, abs=1e-5)
    assert [s["skill"] for s in skills] == ["Python", "SQL", "Airflow"]
    assert [s["weight"] for s in skills] == sorted((s["weight"] for s in skills), reverse=True)


def test_p_role_threshold_is_inclusive_at_exactly_eight_percent(tmp_path):
    # 150 role posts: SQL in 12 (8.0%) passes; Rust in 11 (7.3%) fails. Both have >= 10 posts.
    posts = ["Data Engineer | " + ("SQL" if i < 12 else "") + (" Rust" if i < 11 else "") for i in range(150)]
    posts += ["Other job"] * 150
    doc = learn(tmp_path, spread(_month_list(2), posts))
    names = {s["skill"] for s in doc["roles"][0]["skills"]}
    assert "SQL" in names and "Rust" not in names


def test_min_skill_posts_is_ten(tmp_path):
    # 9 posts is 22.5% of 40 role posts (well above 8%) and lift is high, but 9 < 10 posts.
    def run(n_sql, sub):
        posts = ["Data Engineer | " + ("SQL" if i < n_sql else "") for i in range(40)] + ["Other"] * 200
        return learn(tmp_path / sub, spread(_month_list(2), posts))["roles"][0]["skills"]

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert R.MIN_SKILL_POSTS == 10
    assert run(9, "a") == []
    assert [s["skill"] for s in run(10, "b")] == ["SQL"]


def test_lift_filter_is_inclusive_at_1_2(tmp_path):
    # Role posts: 50, 24 mention SQL (p_role 0.48). Others: 50, 16 mention SQL, so p_all = 0.4 -> lift 1.2.
    posts = ["Data Engineer | SQL"] * 24 + ["Data Engineer"] * 26
    posts += ["Misc | SQL"] * 16 + ["Misc"] * 34
    doc = learn(tmp_path, spread(_month_list(2), posts))
    skills = {s["skill"]: s for s in doc["roles"][0]["skills"]}
    assert skills["SQL"]["lift"] == pytest.approx(1.2)


def test_only_top_ten_skills_are_kept(tmp_path):
    taxonomy = [{"skill": f"S{i:02d}", "pattern": rf"\bs{i:02d}\b", "case_sensitive": False} for i in range(12)]
    posts = []
    for i in range(40):  # skill k appears in 40 - k posts: S00 40 ... S11 29 of 40 role posts
        posts.append("Data Engineer " + " ".join(f"S{k:02d}" for k in range(12) if i < 40 - k))
    posts += ["Other"] * 200  # so lift is high for every skill
    doc = learn(tmp_path, spread(_month_list(2), posts), taxonomy=taxonomy)
    skills = doc["roles"][0]["skills"]
    assert [s["skill"] for s in skills] == [f"S{i:02d}" for i in range(10)]
    assert sum(s["weight"] for s in skills) == pytest.approx(1.0, abs=1e-5)


def test_profiles_use_single_role_posts_only(tmp_path):
    # 20 data-engineer-only posts mention Python. 30 posts name BOTH roles and mention SQL.
    posts = ["Data Engineer | Python"] * 20 + ["Data Engineer or site reliability | SQL"] * 30 + ["Other"] * 100
    doc = learn(tmp_path, spread(_month_list(2), posts))
    by_id = {r["role_id"]: r for r in doc["roles"]}
    de, sre = by_id["de"], by_id["sre"]
    assert (de["n_role_posts"], de["n_single_role_posts"]) == (50, 20)
    assert (sre["n_role_posts"], sre["n_single_role_posts"]) == (30, 0)
    assert [s["skill"] for s in de["skills"]] == ["Python"]  # SQL only appears in the two-role posts
    assert de["skills"][0]["p_role"] == pytest.approx(1.0)  # 20 of the 20 single-role posts
    assert sre["skills"] == []


def test_tier_boundaries():
    assert [R.tier_for(n) for n in (0, 49, 50, 149, 150, 1000)] == [
        "not_ranked", "not_ranked", "rough", "rough", "solid", "solid"]


@pytest.mark.parametrize("n, tier, ranked", [(49, "not_ranked", False), (50, "rough", True),
                                             (149, "rough", True), (150, "solid", True)])
def test_profile_tier_and_note(tmp_path, n, tier, ranked):
    posts = ["Data Engineer | Python"] * n + ["Other"] * 50
    doc = learn(tmp_path, spread(_month_list(2), posts))
    de = doc["roles"][0]
    assert de["n_single_role_posts"] == n
    assert (de["tier"], de["ranked"]) == (tier, ranked)
    if tier == "solid":
        assert de["note"] is None
    else:
        assert str(n) in de["note"]
        assert ("Rough profile" in de["note"]) == (tier == "rough")
        assert ("Not ranked" in de["note"]) == (tier == "not_ranked")


def test_role_marked_ranked_false_in_roles_json_is_never_ranked(tmp_path):
    roles = [dict(ROLES[0], ranked=False, note="Not ranked: too few posts to learn a profile"), ROLES[1]]
    posts = ["Data Engineer | Python"] * 200 + ["Other"] * 50
    doc = learn(tmp_path, spread(_month_list(2), posts), roles=roles)
    de = doc["roles"][0]
    assert de["tier"] == "solid" and de["ranked"] is False
    assert de["note"] == "Not ranked: too few posts to learn a profile"


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
    doc = learn(tmp_path, {"2024-01": posts})
    counts = {r["role_id"]: (r["n_role_posts"], r["n_single_role_posts"]) for r in doc["roles"]}
    assert counts == {"de": (1, 0), "sre": (1, 0)}


def test_profile_lists_the_threads_used(learned):
    doc, by_id = learned
    assert doc["thread_ids"] == ["1", "2", "3", "4"]
    assert set(by_id["de"]["thread_ids"]) <= set(doc["thread_ids"])
    assert by_id["sre"]["thread_ids"] == []


# ---------------------------------------------------------------- as-of profiles

def _profile_doc(tmp_path):
    months = _month_list(8)
    posts = ["Data Engineer | Python"] * 30 + ["Other"] * 30
    raw, threads = write_corpus(tmp_path, spread(months, posts))
    doc = R.learn_profile_set(raw, threads, TAXONOMY, ROLES, ["2024-03", "2024-06", "2024-08"], months=4)
    return doc


def test_learn_profile_set_makes_one_profile_per_point_with_its_own_window(tmp_path):
    doc = _profile_doc(tmp_path)
    assert doc["schema_version"] == 2
    assert doc["as_of_points"] == ["2024-03", "2024-06", "2024-08"]
    assert list(doc["profiles"]) == doc["as_of_points"]
    windows = {p: (v["window"]["from"], v["window"]["to"]) for p, v in doc["profiles"].items()}
    assert windows == {"2024-03": ("2024-01", "2024-03"), "2024-06": ("2024-03", "2024-06"),
                       "2024-08": ("2024-05", "2024-08")}


def test_profile_for_picks_the_latest_point_not_after_as_of(tmp_path):
    doc = _profile_doc(tmp_path)
    assert R.profile_for("2024-03", doc)["as_of"] == "2024-03"
    assert R.profile_for("2024-05", doc)["as_of"] == "2024-03"
    got = R.profile_for("2024-07", doc)
    assert got["as_of"] == "2024-06" and got["window"]["from"] == "2024-03"
    assert got["requested_as_of"] == "2024-07"
    assert R.profile_for("2030-01", doc)["as_of"] == "2024-08"
    with pytest.raises(ValueError, match="2024-03"):
        R.profile_for("2024-02", doc)


def test_a_profile_never_sees_posts_after_its_point(tmp_path):
    # Python appears in role posts only from 2024-05 on. The 2024-03 profile must not know it.
    months = _month_list(6)
    by_month = {m: ["Other"] * 5 for m in months}
    for m in months:
        by_month[m] += ["Data Engineer | Python" if m >= "2024-05" else "Data Engineer"] * 20
    raw, threads = write_corpus(tmp_path, by_month)
    doc = R.learn_profile_set(raw, threads, TAXONOMY, ROLES, ["2024-04", "2024-06"], months=24)
    early = {s["skill"] for s in doc["profiles"]["2024-04"]["roles"][0]["skills"]}
    late = {s["skill"] for s in doc["profiles"]["2024-06"]["roles"][0]["skills"]}
    assert early == set() and late == {"Python"}


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
    assert got == {  # the two-role post counts for both roles in demand
        ("2024-01", "de"): (3, 4), ("2024-01", "sre"): (1, 4),
        ("2024-02", "de"): (0, 3), ("2024-02", "sre"): (0, 3),
    }
    assert rows[0]["share"] == pytest.approx(0.75)
    with out.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["month", "role_id", "mentions", "n_posts", "share"]
        first = next(reader)
    assert first == {"month": "2024-01", "role_id": "de", "mentions": "3", "n_posts": "4", "share": "0.750000"}
    assert R.read_demand_rows(out)[0] == {"month": "2024-01", "role_id": "de", "mentions": 3, "n_posts": 4,
                                          "share": 0.75}


def _demand_rows(role_id, prev, recent, n_posts=300, months=24):
    """24 months: first 12 have `prev` mentions each, last 12 have `recent`."""
    ms = _month_list(months)
    return [{"month": m, "role_id": role_id, "mentions": prev if i < months - 12 else recent,
             "n_posts": n_posts, "share": 0.0} for i, m in enumerate(ms)]


def test_role_trends_use_the_skill_welch_rule():
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
    assert R.build_role_trends(short, [{"id": "r"}])["roles"]["r"]["trend_label"] is None
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
    assert cut["roles"]["r"]["posts_last12"] == 12 * 300


def test_partial_month_flag():
    rows = _demand_rows("r", 10, 10)
    assert R.build_role_trends(rows, [{"id": "r"}], today=datetime(2025, 12, 5, tzinfo=timezone.utc))["partial_month"]


# ---------------------------------------------------------------- match

def _profiles(*roles):
    return {"roles": list(roles)}


def _role(role_id, name, skills, tier="solid", n=200, ranked=True):
    return {"role_id": role_id, "name": name, "description": "d", "sdg": ["8.2"], "tier": tier,
            "ranked": ranked, "note": None, "n_role_posts": n + 10, "n_single_role_posts": n,
            "skills": [{"skill": s, "weight": w} for s, w in skills]}


def _scores(**stances):
    """skill -> (stance, status, trend). Only the fields match_roles reads."""
    return {"scenario_params": {"k": 2},
            "skills": [{"skill": s, "stance": st, "status": status, "trend_label": tr}
                       for s, (st, status, tr) in stances.items()]}


def _trends(**roles):
    """role -> (label, mentions_last12, mentions_prev12); 1000 posts in each year."""
    return {"roles": {rid: {"trend_label": label, "trend_p": 0.01, "mentions_last12": a, "mentions_prev12": b,
                            "posts_last12": 1000, "posts_prev12": 1000}
                      for rid, (label, a, b) in roles.items()}}


SCORES = _scores(
    Python=("AI-substitutable", "ok", "No clear change"),
    SQL=("neutral", "ok", "No clear change"),
    Airflow=("neutral", "low_volume", "Rising"),
    dbt=("neutral", "low_volume", "Rising"),
    LLM=("AI-complement", "ok", "No clear change"),
    RAG=("AI-complement", "ok", "Rising"),
)
SCORES["skills"].append({"skill": "JavaScript / TypeScript", "stance": "AI-substitutable", "status": "ok",
                         "trend_label": "No clear change"})
SCORES["skills"].append({"skill": "TypeScript", "stance": "AI-substitutable", "status": "ok",
                         "trend_label": "Rising"})
DE = _role("de", "Data Engineer", [("Python", 0.4), ("SQL", 0.3), ("Airflow", 0.2), ("dbt", 0.1)])


def test_match_score_is_weight_of_owned_skills_over_total():
    out = R.match_roles({"Python", "SQL"}, _profiles(DE), SCORES, _trends(de=("Rising", 182, 140)))
    role = out["roles"][0]
    assert role["match_score"] == pytest.approx(0.7)
    assert [s["skill"] for s in role["have"]] == ["Python", "SQL"]


def test_match_score_normalises_weights_that_do_not_sum_to_one():
    prof = _role("de", "Data Engineer", [("Python", 2), ("SQL", 1), ("Airflow", 1)])
    assert R.match_roles({"Python"}, _profiles(prof), SCORES, {})["roles"][0]["match_score"] == pytest.approx(0.5)


def test_match_score_extremes_and_empty_profile():
    none = R.match_roles(set(), _profiles(DE), SCORES, {})["roles"][0]
    assert none["match_score"] == 0.0 and none["have"] == []
    all_ = R.match_roles({"Python", "SQL", "Airflow", "dbt"}, _profiles(DE), SCORES, {})["roles"][0]
    assert all_["match_score"] == pytest.approx(1.0) and all_["gap"] == []
    empty = R.match_roles({"Python"}, _profiles(_role("x", "X", [], tier="rough", n=60)), SCORES, {})["roles"][0]
    assert empty["match_score"] == 0.0 and empty["fast_shift"] == 0.0
    assert "No skill profile" in empty["reason"]


def test_skills_the_roles_do_not_use_are_ignored_for_the_score():
    out = R.match_roles({"Python", "Cobol"}, _profiles(DE), SCORES, {})
    assert out["roles"][0]["match_score"] == pytest.approx(0.4)


def test_unmatched_lists_user_skills_not_in_the_taxonomy():
    out = R.match_roles({"Python", "Cobol", "Fortran"}, _profiles(DE), SCORES, {})
    assert out["unmatched"] == ["Cobol", "Fortran"]
    assert R.match_roles({"Python"}, _profiles(DE), SCORES, {})["unmatched"] == []


def test_a_plain_string_is_rejected():
    with pytest.raises(TypeError, match="not a string"):
        R.match_roles("Python", _profiles(DE), SCORES, {})
    assert R.match_roles(["Python"], _profiles(DE), SCORES, {})["roles"]  # a list is fine
    assert R.match_roles(("Python",), _profiles(DE), SCORES, {})["roles"]


def test_user_skills_as_dict_keeps_years():
    out = R.match_roles({"Python": 3, "SQL": 1.5}, _profiles(DE), SCORES, {})["roles"][0]
    assert {s["skill"]: s["years"] for s in out["have"]} == {"Python": 3, "SQL": 1.5}


def test_typescript_counts_as_javascript_typescript():
    prof = _role("fs", "Full", [("JavaScript / TypeScript", 0.6), ("Python", 0.4)])
    role = R.match_roles({"TypeScript"}, _profiles(prof), SCORES, {})["roles"][0]
    assert role["match_score"] == pytest.approx(0.6)
    assert [s["skill"] for s in role["have"]] == ["JavaScript / TypeScript"]


def test_profile_with_both_rows_is_merged_so_there_is_no_typescript_gap():
    prof = _role("fs", "Full", [("JavaScript / TypeScript", 0.3), ("TypeScript", 0.2), ("React", 0.5)])
    role = R.match_roles({"JavaScript / TypeScript"}, _profiles(prof), SCORES, {})["roles"][0]
    assert [s["skill"] for s in role["gap"]] == ["React"]
    assert role["have"][0]["weight"] == pytest.approx(0.5)  # 0.3 + 0.2 merged into the combined row
    assert role["match_score"] == pytest.approx(0.5)
    assert role["n_profile_skills"] == 2
    assert "TypeScript" not in {s["skill"] for s in role["have"] + role["gap"]}


def test_typescript_alone_in_a_profile_stays_as_typescript():
    prof = _role("fs", "Full", [("TypeScript", 0.5), ("React", 0.5)])
    role = R.match_roles({"JavaScript / TypeScript"}, _profiles(prof), SCORES, {})["roles"][0]
    assert [s["skill"] for s in role["gap"]] == ["React", "TypeScript"]  # no merge: the profile has no combined row
    assert role["match_score"] == 0.0


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


@pytest.mark.parametrize("label, expected", [("Rising", 1.0), ("No clear change", 0.5), ("Falling", 0.0),
                                             (None, 0.5)])
def test_future_score_from_trend(label, expected):
    out = R.match_roles({"Python"}, _profiles(DE), SCORES, _trends(de=(label, 10, 10)))
    role = out["roles"][0]
    assert role["future_score"] == expected
    assert role["rank_score"] == pytest.approx(0.7 * 0.4 + 0.3 * expected)


def test_missing_trend_entry_counts_as_unknown():
    role = R.match_roles({"Python"}, _profiles(DE), SCORES, {})["roles"][0]
    assert role["future_score"] == 0.5
    assert role["outlook"]["trend_label"] is None


def test_no_fast_adjustment_exists_and_rank_is_the_same_in_both_scenarios():
    assert not hasattr(R, "FAST_ADJUSTMENT")
    ai = _role("ai", "AI", [("LLM", 0.4), ("RAG", 0.3), ("SQL", 0.3)])
    sub = _role("sub", "Sub", [("Python", 0.6), ("SQL", 0.4)])
    mix = _role("mix", "Mix", [("Python", 0.5), ("LLM", 0.5)])
    trends = _trends(ai=("Rising", 1, 1), sub=("Falling", 1, 1), mix=("No clear change", 1, 1))
    prof = _profiles(ai, sub, mix)
    mod = R.match_roles({"SQL"}, prof, SCORES, trends, "moderate")
    fast = R.match_roles({"SQL"}, prof, SCORES, trends, "fast")
    assert [r["role_id"] for r in mod["roles"]] == [r["role_id"] for r in fast["roles"]]
    for a, b in zip(mod["roles"], fast["roles"]):
        assert a["rank_score"] == b["rank_score"] and a["future_score"] == b["future_score"]
        assert a["rank_score"] == pytest.approx(0.7 * a["match_score"] + 0.3 * a["future_score"])
    assert "scenario_adjustment" not in mod["roles"][0]


def test_fast_shift_is_minus_k_times_weighted_exposure():
    ai = _role("ai", "AI", [("LLM", 0.4), ("RAG", 0.3), ("SQL", 0.3)])
    exposure = {"LLM": -0.10, "RAG": -0.10, "SQL": 0.0, "Python": 0.02}
    out = R.match_roles(set(), _profiles(ai), SCORES, {}, "fast", exposure=exposure)
    assert out["roles"][0]["fast_shift"] == pytest.approx(-2 * (0.4 * -0.10 + 0.3 * -0.10))  # +0.14
    assert out["roles"][0]["fast_shift"] > 0
    sub = _role("sub", "Sub", [("Python", 1.0)])
    assert R.match_roles(set(), _profiles(sub), SCORES, {}, exposure=exposure)["roles"][0]["fast_shift"] \
        == pytest.approx(-0.04)
    # k comes from skill_scores unless given
    assert R.match_roles(set(), _profiles(sub), SCORES, {}, exposure=exposure, k=3)["roles"][0]["fast_shift"] \
        == pytest.approx(-0.06)


def test_fast_shift_default_exposure_is_ai_exposure_minus_its_mean():
    scores = {"scenario_params": {"k": 2}, "skills": [
        {"skill": "A", "ai_exposure": 0.7}, {"skill": "B", "ai_exposure": 0.3}]}
    prof = _role("x", "X", [("A", 0.5), ("B", 0.5)])
    assert R.match_roles(set(), _profiles(prof), scores, {})["roles"][0]["fast_shift"] == pytest.approx(0.0)
    prof = _role("x", "X", [("A", 1.0)])
    assert R.match_roles(set(), _profiles(prof), scores, {})["roles"][0]["fast_shift"] == pytest.approx(-0.4)


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="scenario"):
        R.match_roles(set(), _profiles(DE), SCORES, {}, "slow")


def test_unranked_roles_are_left_out_of_the_ranking_and_listed():
    thin = _role("thin", "Thin", [("Python", 1.0)], tier="not_ranked", n=20, ranked=False)
    off = _role("off", "Off", [("Python", 1.0)], ranked=False)
    off["note"] = "Not ranked: too few posts to learn a profile"
    out = R.match_roles({"Python"}, _profiles(DE, thin, off), SCORES, {})
    assert [r["role_id"] for r in out["roles"]] == ["de"]
    assert {r["role_id"] for r in out["not_ranked"]} == {"thin", "off"}
    assert next(r for r in out["not_ranked"] if r["role_id"] == "off")["note"].startswith("Not ranked")


def test_ranking_order_and_rank_numbers():
    a = _role("a", "Alpha", [("Python", 1.0)])
    b = _role("b", "Beta", [("SQL", 1.0)])
    c = _role("c", "Gamma", [("Airflow", 1.0)])
    trends = _trends(a=("Falling", 1, 1), b=("Rising", 1, 1), c=("Rising", 1, 1))
    out = R.match_roles({"Python"}, _profiles(a, b, c), SCORES, trends)
    assert [r["name"] for r in out["roles"]] == ["Alpha", "Beta", "Gamma"]  # Beta/Gamma tie: name order
    assert [r["rank"] for r in out["roles"]] == [1, 2, 3]
    assert out["roles"][0]["rank_score"] == pytest.approx(0.7)
    assert out["roles"][1]["rank_score"] == pytest.approx(0.3)


def test_future_can_outrank_a_small_match_advantage():
    hi = _role("hi", "Hi", [("Python", 0.5), ("SQL", 0.5)])  # match 0.5, Falling -> 0.35
    lo = _role("lo", "Lo", [("Python", 0.4), ("SQL", 0.6)])  # match 0.4, Rising -> 0.58
    out = R.match_roles({"Python"}, _profiles(hi, lo), SCORES, _trends(hi=("Falling", 1, 1), lo=("Rising", 1, 1)))
    assert [r["role_id"] for r in out["roles"]] == ["lo", "hi"]


def test_output_states_the_team_judgement_constants():
    f = R.match_roles(set(), _profiles(DE), SCORES, {})["formula"]
    assert (f["match_weight"], f["future_weight"]) == (0.7, 0.3)
    assert "team judgement" in f["basis"]
    assert "never used in rank_score" in f["fast_shift"]


def test_reason_string_uses_shares_not_counts():
    out = R.match_roles({"Python", "SQL"}, _profiles(DE), SCORES, _trends(de=("Rising", 106, 94)))
    assert out["roles"][0]["reason"] == (
        "You have 2 of its top 4 skills (Python, SQL). Biggest gaps: Airflow, dbt. "
        "Role demand: Rising (10.6% of posts vs 9.4% the year before)."
    )


def test_reason_for_no_overlap_no_gap_no_trend_and_rough():
    none = R.match_roles(set(), _profiles(DE), SCORES, {})["roles"][0]["reason"]
    assert none.startswith("You have none of its top 4 skills.")
    assert "Role demand: too few posts to label a trend." in none
    full = R.match_roles({"Python", "SQL", "Airflow", "dbt"}, _profiles(DE), SCORES, {})["roles"][0]["reason"]
    assert "No gaps among its top skills." in full
    rough = _role("t", "T", [("Python", 1.0)], tier="rough", n=60)
    reason = R.match_roles({"Python"}, _profiles(rough), SCORES, {})["roles"][0]["reason"]
    assert reason.endswith("Rough profile: learned from 60 single-role posts.")


def test_reason_without_post_counts_falls_back_to_the_label():
    trends = {"roles": {"de": {"trend_label": "Rising", "mentions_last12": 5, "mentions_prev12": 3}}}
    reason = R.match_roles({"Python"}, _profiles(DE), SCORES, trends)["roles"][0]["reason"]
    assert reason.endswith("Role demand: Rising.")


def test_reason_shows_at_most_four_skills_and_three_gaps():
    prof = _role("x", "X", [(f"S{i}", 1 - i * 0.05) for i in range(10)])
    reason = R.match_roles({f"S{i}" for i in range(5)}, _profiles(prof), SCORES, {})["roles"][0]["reason"]
    assert "You have 5 of its top 10 skills (S0, S1, S2, S3)." in reason
    assert "Biggest gaps: S5, S6, S7." in reason


def test_accepts_bare_lists_and_mappings():
    out = R.match_roles({"Python"}, [DE], SCORES["skills"], _trends(de=("Rising", 2, 1))["roles"])
    assert out["roles"][0]["outlook"]["trend_label"] == "Rising"


# ---------------------------------------------------------------- committed files (real data)

needs_files = pytest.mark.skipif(
    not all((DATA / n).exists() for n in ("role_profiles.json", "role_trends.json", "role_demand_monthly.csv",
                                          "skill_scores.json", "exposure.csv")),
    reason="generated role files not built yet")


@pytest.fixture(scope="module")
def real_files():
    load = lambda n: json.loads((DATA / n).read_text(encoding="utf-8"))  # noqa: E731
    return {"profiles": load("role_profiles.json"), "trends": load("role_trends.json"),
            "scores": load("skill_scores.json"), "exposure": R.load_exposure(DATA / "exposure.csv"),
            "rows": R.read_demand_rows(DATA / "role_demand_monthly.csv"), "roles": R.load_roles()}


def _real_match(files, skills, as_of="2026-10", scenario="moderate"):
    profile = R.profile_for(as_of, files["profiles"])
    trends = R.build_role_trends(files["rows"], files["roles"], as_of=as_of)
    return R.match_roles(skills, profile, files["scores"], trends, scenario, exposure=files["exposure"])


@needs_files
def test_committed_profiles_are_consistent(real_files):
    doc = real_files["profiles"]
    assert doc["schema_version"] == 2
    assert doc["as_of_points"] == list(R.PROFILE_AS_OF_POINTS)
    for point, profile in doc["profiles"].items():
        assert profile["as_of"] == point and profile["window"]["to"] == point
        assert profile["window"]["months"] == 24
        for role in profile["roles"]:
            assert role["tier"] == R.tier_for(role["n_single_role_posts"])
            assert role["n_single_role_posts"] <= role["n_role_posts"]
            assert len(role["skills"]) <= 10
            if role["skills"]:
                assert sum(s["weight"] for s in role["skills"]) == pytest.approx(1.0, abs=1e-4)
            for s in role["skills"]:
                assert s["p_role"] >= 0.08 - 1e-9 and s["lift"] >= 1.2 - 1e-3
                assert s["single_role_posts"] >= R.MIN_SKILL_POSTS


@needs_files
def test_latest_profile_has_eight_ranked_roles_and_analytics_engineer_is_dropped(real_files):
    out = _real_match(real_files, PERSONAS["Aina"])
    assert len(out["roles"]) == 8
    assert "Analytics Engineer" not in {r["name"] for r in out["roles"]}
    assert "Data Scientist" in {r["name"] for r in out["roles"]}
    assert [r["role_id"] for r in out["not_ranked"]] == ["analytics_engineer"]
    assert out["not_ranked"][0]["note"] == "Not ranked: too few posts to learn a profile"
    assert {r["tier"] for r in out["roles"]} <= {"solid", "rough"}
    ranks = [r["rank_score"] for r in out["roles"]]
    assert ranks == sorted(ranks, reverse=True) and all(0.0 <= r <= 1.0 for r in ranks)


@needs_files
def test_fast_shift_for_ai_app_engineer_is_positive_on_the_real_profile(real_files):
    out = _real_match(real_files, PERSONAS["Aina"], scenario="fast")
    shifts = {r["role_id"]: r["fast_shift"] for r in out["roles"]}
    assert shifts["ai_app_engineer"] > 0
    assert all(abs(v) < 0.5 for v in shifts.values())


@needs_files
def test_default_exposure_matches_exposure_csv(real_files):
    with_csv = _real_match(real_files, PERSONAS["Aina"])
    profile = R.profile_for("2026-10", real_files["profiles"])
    trends = R.build_role_trends(real_files["rows"], real_files["roles"], as_of="2026-10")
    derived = R.match_roles(PERSONAS["Aina"], profile, real_files["scores"], trends)
    assert {r["role_id"]: r["fast_shift"] for r in with_csv["roles"]} == pytest.approx(
        {r["role_id"]: r["fast_shift"] for r in derived["roles"]}, abs=1e-5)


@needs_files
def test_scenario_never_changes_the_ranking_on_real_data(real_files):
    for skills in PERSONAS.values():
        mod = _real_match(real_files, skills, scenario="moderate")
        fast = _real_match(real_files, skills, scenario="fast")
        assert [r["role_id"] for r in mod["roles"]] == [r["role_id"] for r in fast["roles"]]
        assert [r["rank_score"] for r in mod["roles"]] == [r["rank_score"] for r in fast["roles"]]


@needs_files
def test_typescript_user_has_no_typescript_gap_on_real_profiles(real_files):
    out = _real_match(real_files, PERSONAS["Ben"])
    for role in out["roles"]:
        have = {s["skill"] for s in role["have"]}
        gap = {s["skill"] for s in role["gap"]}
        if "JavaScript / TypeScript" in have:
            assert "TypeScript" not in gap, role["name"]


@needs_files
def test_committed_role_trends_equal_a_rebuild_from_the_csv(real_files):
    rebuilt = R.build_role_trends(real_files["rows"], real_files["roles"])
    committed = real_files["trends"]
    assert committed["as_of"] == rebuilt["as_of"]
    assert committed["roles"] == rebuilt["roles"]


@needs_files
def test_an_as_of_cut_changes_the_ranking_for_at_least_one_persona(real_files):
    changed = []
    for name, skills in PERSONAS.items():
        late = [r["role_id"] for r in _real_match(real_files, skills, "2026-10")["roles"]]
        early = [r["role_id"] for r in _real_match(real_files, skills, "2023-12")["roles"]]
        if early != late:
            changed.append(name)
    assert changed


@needs_files
def test_as_of_trends_use_only_data_up_to_as_of(real_files):
    cut = R.build_role_trends(real_files["rows"], real_files["roles"], as_of="2023-12")
    later = [r for r in real_files["rows"] if r["month"] <= "2023-12"]
    assert cut["as_of"] == "2023-12"
    assert cut["roles"] == R.build_role_trends(later, real_files["roles"])["roles"]
    assert cut["roles"]["backend_engineer"]["posts_last12"] == sum(
        r["n_posts"] for r in later if r["role_id"] == "backend_engineer" and r["month"] >= "2023-01")


@needs_files
def test_demo_personas_have_matching_reasons(real_files):
    for skills in PERSONAS.values():
        for role in _real_match(real_files, skills)["roles"]:
            assert role["reason"].startswith("You have")
            assert "% of posts vs" in role["reason"] or "too few posts" in role["reason"]


# ---------------------------------------------------------------- privacy and main

def test_no_post_text_reaches_any_output_file(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("taxonomy.json", "roles.json"):
        shutil.copy(DATA / name, data_dir / name)
    months = _month_list(26)
    posts = [f"Acme | Data Engineer | Python SQL | {SENTINEL}", f"Beta | ML Engineer | {SENTINEL}",
             "Gamma | Backend Engineer | Go", "Plain post"] * 3
    raw, threads = write_corpus(tmp_path, {m: list(posts) for m in months})
    assert R.main(["--raw-dir", str(raw), "--threads-csv", str(threads), "--data-dir", str(data_dir),
                   "--as-of", "2025-06", "--as-of", "2026-02"]) == 0

    written = [data_dir / n for n in ("role_profiles.json", "role_demand_monthly.csv", "role_trends.json")]
    assert all(p.exists() for p in written)
    for path in written:
        content = path.read_text(encoding="utf-8")
        assert "ZZSECRET" not in content and "jane.doe" not in content and "example.test" not in content, path.name
        assert "Acme" not in content and "Gamma" not in content and "Plain post" not in content, path.name
    doc = json.loads(written[0].read_text(encoding="utf-8"))
    assert doc["as_of_points"] == ["2025-06", "2026-02"]
    allowed = {"role_id", "name", "description", "sdg", "n_role_posts", "n_single_role_posts", "window", "tier",
               "ranked", "note", "skills", "thread_ids"}
    for profile in doc["profiles"].values():
        assert all(set(r) == allowed for r in profile["roles"])
        assert all(set(s) == {"skill", "weight", "p_role", "p_all", "lift", "single_role_posts"}
                   for r in profile["roles"] for s in r["skills"])
    latest = doc["profiles"]["2026-02"]
    de = next(r for r in latest["roles"] if r["role_id"] == "data_engineer")
    assert de["n_role_posts"] == de["n_single_role_posts"] == 3 * 24 and de["tier"] == "rough"
    # Python and SQL in 3 of 3 data-engineer posts each; the title is masked.
    assert {s["skill"] for s in de["skills"]} == {"Python", "SQL"}
    trends = json.loads(written[2].read_text(encoding="utf-8"))
    assert trends["roles"]["data_engineer"]["trend_label"] == "No clear change"
