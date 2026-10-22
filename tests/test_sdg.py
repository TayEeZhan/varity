"""Tests for engine.sdg: sector patterns, perks handling, aggregation, privacy, rerank and plan lines."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine import sdg
from engine.sdg import (
    GOAL_WEIGHT,
    MAX_EXCESS,
    MIN_EMPLOYERS,
    MIN_N,
    load_sectors,
    plan_sdg_summary,
    rerank_for_goal,
    role_sdg_profile,
    scan_sdg,
    sector_tags,
    skill_sdg_profile,
    strip_perks,
    wilson_interval,
)

SECTORS = load_sectors()
SECTOR_IDS = [s["id"] for s in SECTORS["sectors"]]


# ---------------------------------------------------------------- sector patterns

# (sector, sentence that must tag it)
POSITIVE = [
    ("climate_energy", "We build software for solar and wind developers."),
    ("climate_energy", "Climate tech startup. Help us decarbonize buildings."),
    ("climate_energy", "Battery management systems for grid-scale energy storage."),
    ("climate_energy", "Carbon accounting for the power grid."),
    ("climate_energy", "Our EV charging network needs a backend engineer."),
    ("health", "We build EHR integrations for hospitals and clinics."),
    ("health", "Help patients get care: telehealth platform."),
    ("health", "Biotech company applying machine learning to drug discovery."),
    ("health", "Healthcare data platform, HIPAA compliant."),
    ("health", "We build tools for hospitals, clinics and labs."),
    ("education", "We are an edtech company for K-12 classrooms."),
    ("education", "We help teachers and students with an online learning platform."),
    ("education", "Our learning management system serves universities."),
    ("financial_inclusion", "Financial inclusion for the underbanked in emerging markets."),
    ("financial_inclusion", "Payments for small businesses and microfinance lenders."),
    ("financial_inclusion", "Mobile money and cross-border remittances in Africa."),
    ("agriculture_food", "Precision agriculture software for farmers."),
    ("agriculture_food", "AgTech startup working on food security."),
    ("government_civic", "We sell to state and local government agencies."),
    ("government_civic", "Civic tech for municipal services and elections."),
    ("government_civic", "GovTech: modernising the public sector."),
    ("accessibility", "We make assistive technology for people with disabilities."),
    ("accessibility", "Digital accessibility testing for the web."),
    ("cities_mobility", "Public transit agencies use our rider app."),
    ("cities_mobility", "Urban mobility and e-bikes for smart cities."),
    ("cities_mobility", "Affordable housing platform."),
]

# (sector, sentence that must NOT tag it)
NEGATIVE = [
    ("climate_energy", "Our political climate is fine; we ship weekly."),
    ("climate_energy", "Experience with Carbon Design System and CSS grid layouts."),
    ("climate_energy", "Fix battery drain in our mobile app."),
    ("climate_energy", "Data stored in a data grid with AG Grid."),
    ("health", "Benefits: health insurance, dental, vision, 401k."),
    ("health", "We offer healthcare, dental and a gym stipend."),
    ("health", "Competitive salary, health benefits and healthcare coverage."),
    ("health", "Our culture is healthy and we ship fast."),
    ("health", "We are a hospitality software company."),
    ("health", "Our stack runs on AWS with EMR, RDS and Lambda."),
    ("health", "We serve sectors like pharmaceuticals, energy, and manufacturing."),
    ("health", "Smart vehicles, rockets, medical devices, robotics, and much more."),
    ("health", "Experience with HIPAA is a plus."),
    ("education", "Real-time machine learning platform for fraud detection."),
    ("education", "We like old school engineering and grad school hires."),
    ("education", "Internship open to students graduating in 2026."),
    ("financial_inclusion", "Reporting and billing: ensure timely remittance of funds."),
    ("financial_inclusion", "We are a payments company for enterprises."),
    ("agriculture_food", "We run a build farm and a server farm."),
    ("agriculture_food", "Food delivery for busy people."),
    ("government_civic", "Government ID is required for the background check."),
    ("government_civic", "Topics: leader election, consensus and fault detection."),
    ("government_civic", "Ability to obtain and maintain a government clearance."),
    ("government_civic", "Customers include banks, retailers, and government agencies."),
    ("accessibility", "We are an equal opportunity employer and do not discriminate on disability."),
    ("accessibility", "Qualified individuals with disabilities will receive reasonable accommodations."),
    ("accessibility", "Make 3D accessible to everyone."),
    ("accessibility", "Experience with web accessibility standards and WCAG is a plus."),
    ("cities_mobility", "Data in transit is encrypted with TLS."),
    ("cities_mobility", "Career mobility and urban legends are not our thing."),
    ("cities_mobility", "Turo is a car-sharing marketplace."),
    ("cities_mobility", "We cover disaster relief, insurance, smart cities, and more."),
    ("cities_mobility", "We back sustainable development goals in our office."),
]


@pytest.mark.parametrize("sector,text", POSITIVE)
def test_sector_pattern_positive(sector, text):
    assert sector in sector_tags(text, SECTORS)


@pytest.mark.parametrize("sector,text", NEGATIVE)
def test_sector_pattern_negative(sector, text):
    assert sector not in sector_tags(text, SECTORS)


def test_every_sector_has_a_positive_and_a_negative_test():
    assert {s for s, _ in POSITIVE} == set(SECTOR_IDS)
    assert {s for s, _ in NEGATIVE} == set(SECTOR_IDS)


def test_sector_file_is_well_formed():
    assert 8 <= len(SECTOR_IDS) <= 10
    assert len(set(SECTOR_IDS)) == len(SECTOR_IDS)
    for sector in SECTORS["sectors"]:
        assert sector["sdg"] and all(re.fullmatch(r"\d+(\.\w+)?", t) for t in sector["sdg"])
        assert sector["patterns"]


def test_sector_tags_handles_html_and_empty_text():
    assert sector_tags("", SECTORS) == set()
    assert sector_tags("Acme | Remote<p>We build <i>solar</i> software &amp; hospitals&#x27; tools", SECTORS) \
        == {"climate_energy", "health"}


def test_patterns_use_word_boundaries():
    assert sector_tags("hospitality and presolar", SECTORS) == set()


# ---------------------------------------------------------------- perks and legal lines

def test_benefits_line_does_not_tag_health():
    assert sector_tags("Acme | Remote\nWe build compilers.\nBenefits: healthcare, dental, 401k", SECTORS) == set()


def test_benefits_section_items_are_ignored_until_a_long_line():
    text = ("Acme | Remote\nWe build compilers.\nBenefits\n* Healthcare for you and family\n* Mental health days\n"
            "* Unlimited PTO\n" + "Apply by email with a short note about yourself and the compiler work you did. " * 2
            + "\nWe also help patients.")
    tags = sector_tags(text, SECTORS)
    assert tags == {"health"}  # only the sentence after the section counts
    without = text.replace("\nWe also help patients.", "")
    assert sector_tags(without, SECTORS) == set()


def test_inline_perks_and_we_offer_are_cut_but_the_rest_of_the_line_stays():
    assert sector_tags("Acme | Perks: healthcare, gym | We build solar trackers", SECTORS) == {"climate_energy"}
    assert sector_tags("We build solar trackers. We offer healthcare and equity. Apply by email.", SECTORS) \
        == {"climate_energy"}
    assert sector_tags("We offer healthcare and equity.\nWe build solar trackers.", SECTORS) == {"climate_energy"}


def test_equal_opportunity_line_is_ignored():
    text = "We build compilers.\nWe are an equal opportunity employer. We welcome people with disabilities."
    assert sector_tags(text, SECTORS) == set()


def test_strip_perks_keeps_company_description():
    rules = SECTORS["text_rules"]
    out = strip_perks("Acme\nBenefits:\n* health insurance\nWe build solar panels for farms.", rules)
    assert "solar" in out and "insurance" not in out


def test_health_in_the_company_description_survives_a_perks_section():
    text = "We build tools for hospitals.\nPerks:\n* gym\n* healthcare"
    assert sector_tags(text, SECTORS) == {"health"}


# ---------------------------------------------------------------- fixtures for aggregation

ROLES = [
    {"id": "data_engineer", "name": "Data Engineer", "title_pattern": r"\bdata[\s-]+engineers?\b",
     "description": "d", "sdg": ["8.2"]},
    {"id": "ml_engineer", "name": "ML Engineer", "title_pattern": r"\bml[\s-]+engineers?\b",
     "description": "d", "sdg": ["9.5"], "ranked": False},
]
TAXONOMY = [
    {"skill": "Python", "pattern": r"\bpython\b", "case_sensitive": False},
    {"skill": "Rust", "pattern": r"\brust\b", "case_sensitive": False},
]

PREV_POSTS = [
    "ZetaCorp | Data Engineer | Remote<p>We build solar forecasting. Python.",
    "Omega | Backend dev<p>Hospital software in Rust.",
]
RECENT_POSTS = [
    "AcmeSecret | Data Engineer | Remote<p>Climate tech: we help decarbonize the power grid. Python.",
    "BetaSecret | Data Engineer<p>We build tools for patients and hospitals. Python and Rust.",
    "GammaSecret | Data Engineer or ML Engineer<p>Solar developers use our platform.",
    "DeltaSecret | Data Engineer<p>Compiler team.<p>Benefits: healthcare, dental.",
    "EpsilonSecret | Platform dev<p>We build edtech for teachers. Python.",
]


@pytest.fixture()
def corpus(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    rows = []
    for tid, month, posts in (("1", "2025-01", PREV_POSTS), ("2", "2025-02", RECENT_POSTS)):
        children = [{"id": i, "text": t} for i, t in enumerate(posts)]
        children.append({"id": 99, "deleted": True, "text": "deleted solar"})
        children.append({"id": 98, "text": "   "})
        (raw / f"{tid}.json").write_text(json.dumps({"children": children}), encoding="utf-8")
        rows.append(f"{tid},{month},{month}-01T00:00:00Z,Ask HN {month},https://news.ycombinator.com/item?id={tid},{len(posts)}")
    csv_path = tmp_path / "threads.csv"
    csv_path.write_text("thread_id,month,created_at,title,url,n_top_level\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return raw, csv_path


@pytest.fixture()
def role_doc(corpus):
    raw, csv_path = corpus
    return role_sdg_profile(raw, csv_path, ROLES, SECTORS, months=1)


# ---------------------------------------------------------------- aggregation

def test_scan_counts(corpus):
    raw, csv_path = corpus
    threads = sdg._read_threads(csv_path)
    scan = scan_sdg(raw, threads, ROLES, TAXONOMY, SECTORS)
    recent = scan[1]
    assert recent["n_posts"] == 5
    assert recent["sectors"] == {"climate_energy": 2, "health": 1, "education": 1}
    de = recent["roles"]["data_engineer"]
    assert (de["n"], de["single"]) == (4, 3)  # the Gamma post names two roles: counted in n, not in single
    assert de["sectors"] == {"climate_energy": 1, "health": 1}
    py = recent["skills"]["Python"]
    assert py["n"] == 3 and py["sectors"] == {"climate_energy": 1, "health": 1, "education": 1}
    assert py["employers"]["education"] == {"epsilonsecret"}


def test_role_profile_shares_and_baseline(role_doc):
    assert role_doc["as_of"] == "2025-02"
    base = role_doc["baseline"]
    assert (base["n_recent"], base["n_prev"]) == (5, 2)
    assert base["sectors"]["climate_energy"]["share_recent"] == pytest.approx(0.4)
    assert base["sectors"]["climate_energy"]["share_prev"] == pytest.approx(0.5)
    de = role_doc["roles"]["data_engineer"]
    assert (de["n_recent"], de["n_prev"], de["n_role_posts_recent"]) == (3, 1, 4)
    clim = de["sectors"]["climate_energy"]
    assert clim["count_recent"] == 1 and clim["share_recent"] == pytest.approx(1 / 3)
    assert clim["count_prev"] == 1 and clim["share_prev"] == pytest.approx(1.0)
    assert clim["lift"] == pytest.approx((1 / 3) / 0.4, abs=1e-3)
    assert de["sectors"]["health"]["count_recent"] == 1  # the benefits line did not add a health tag
    assert de["sectors"]["accessibility"]["share_recent"] == 0.0
    assert role_doc["roles"]["ml_engineer"]["ranked"] is False
    assert role_doc["roles"]["ml_engineer"]["n_recent"] == 0
    assert role_doc["roles"]["ml_engineer"]["sectors"]["health"]["share_recent"] is None


def test_small_samples_are_not_reliable(role_doc):
    assert 3 < MIN_N and all(not v["reliable"] for v in role_doc["roles"]["data_engineer"]["sectors"].values())


def test_employers_are_counted_once_each(role_doc):
    de = role_doc["roles"]["data_engineer"]["sectors"]
    assert de["climate_energy"]["employers_recent"] == 1 and de["health"]["employers_recent"] == 1
    assert de["education"]["employers_recent"] == 0
    base = role_doc["baseline"]["sectors"]
    assert base["climate_energy"]["count_recent"] == 2 and base["climate_energy"]["employers_recent"] == 2


def test_employer_key():
    assert sdg.employer_key("Acme Inc. | Remote | Data Engineer\nWe build things") == "acme inc"
    assert sdg.employer_key("\n\n  Beta (YC S21) - Senior Engineer") == "beta yc s21"
    assert sdg.employer_key("") == ""


def test_reliable_needs_enough_posts_and_different_employers():
    base = sdg._entity_doc(["x"], {"x": 50}, {}, 1000, 1000, None, None, {"x": 40})
    def reliable(n, count, employers):
        doc = sdg._entity_doc(["x"], {"x": count}, {}, n, n, base, {}, {"x": employers})
        return doc["sectors"]["x"]["reliable"]
    assert reliable(100, 10, 3) is True
    assert reliable(100, 10, 2) is False  # one employer reposting every month is not a pattern
    assert reliable(MIN_N - 1, 10, 5) is False
    assert MIN_EMPLOYERS == 3


def test_example_threads_are_thread_urls_only(role_doc):
    clim = role_doc["roles"]["data_engineer"]["sectors"]["climate_energy"]
    assert clim["example_threads"] == ["https://news.ycombinator.com/item?id=2"]
    assert role_doc["roles"]["data_engineer"]["sectors"]["education"]["example_threads"] == []
    for role in role_doc["roles"].values():
        for entry in role["sectors"].values():
            assert len(entry["example_threads"]) <= sdg.EXAMPLE_THREADS
            assert all(re.fullmatch(r"https://news\.ycombinator\.com/item\?id=\d+", u) for u in entry["example_threads"])


def test_skill_profile(corpus):
    raw, csv_path = corpus
    doc = skill_sdg_profile(raw, csv_path, TAXONOMY, SECTORS, months=1)
    py = doc["skills"]["Python"]
    assert (py["n_recent"], py["n_prev"]) == (3, 1)
    assert py["sectors"]["health"]["count_recent"] == 1
    assert py["sectors"]["climate_energy"]["share_recent"] == pytest.approx(1 / 3)
    assert py["sectors"]["climate_energy"]["share_prev"] == pytest.approx(1.0)
    rust = doc["skills"]["Rust"]
    assert (rust["n_recent"], rust["n_prev"]) == (1, 1)
    assert rust["sectors"]["health"]["share_prev"] == pytest.approx(1.0)


def test_scan_can_be_reused_and_gives_the_same_answer(corpus):
    raw, csv_path = corpus
    scan = scan_sdg(raw, sdg._read_threads(csv_path), ROLES, TAXONOMY, SECTORS)
    again = role_sdg_profile(raw, csv_path, ROLES, SECTORS, months=1, scan=scan)
    fresh = role_sdg_profile(raw, csv_path, ROLES, SECTORS, months=1)
    for doc in (again, fresh):
        doc.pop("generated_at")
    assert again == fresh


def test_as_of_never_uses_later_posts(corpus):
    raw, csv_path = corpus
    doc = role_sdg_profile(raw, csv_path, ROLES, SECTORS, months=1, as_of="2025-01")
    assert doc["as_of"] == "2025-01"
    assert doc["baseline"]["n_recent"] == 2 and doc["baseline"]["n_prev"] == 0
    assert doc["window"]["previous"] is None


def test_outputs_hold_no_post_text_or_company_names(corpus, role_doc):
    raw, csv_path = corpus
    skill_doc = skill_sdg_profile(raw, csv_path, TAXONOMY, SECTORS, months=1)
    blob = json.dumps([role_doc, skill_doc])
    for post in PREV_POSTS + RECENT_POSTS:
        for company in re.findall(r"^(\w+)", post):
            assert company not in blob
        assert post not in blob
    for phrase in ("decarbonize", "forecasting", "compiler", "Hospital software", "tools for patients"):
        assert phrase not in blob
    # only aggregates: numbers, bools, ids, names of sectors/roles/skills, thread URLs
    urls = set(re.findall(r"https?://[^\"]+", blob))
    assert urls and all(u.startswith("https://news.ycombinator.com/item?id=") and "&" not in u for u in urls)


def test_committed_outputs_hold_aggregates_only():
    for name in ("role_sdg.json", "skill_sdg.json"):
        path = Path(__file__).resolve().parent.parent / "data" / name
        if not path.exists():
            pytest.skip(f"{name} not built yet")
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text)
        assert doc["schema_version"] == sdg.SCHEMA_VERSION
        for url in re.findall(r"https?://[^\"]+", text):
            assert re.fullmatch(r"https://news\.ycombinator\.com/item\?id=\d+", url)
        assert len(text) < 400_000  # no text dump hides in here


def test_wilson_interval():
    assert wilson_interval(0, 0) is None
    lo, hi = wilson_interval(10, 100)
    assert lo < 0.1 < hi and 0 <= lo and hi <= 1
    lo0, hi0 = wilson_interval(0, 20)
    assert lo0 == 0.0 and 0 < hi0 < 0.2


# ---------------------------------------------------------------- rerank_for_goal

def _role_sdg(lifts: dict[str, tuple[float | None, int, int, bool]], baseline_share: float = 0.1) -> dict:
    """Small hand-made role_sdg doc. lifts[role_id] = (share, count, n, reliable)."""
    sectors = [{"id": "climate_energy", "name": "Climate and clean energy", "sdg": ["7.2", "13.2"]},
               {"id": "health", "name": "Health and life sciences", "sdg": ["3.8", "3.b"]}]
    roles = {}
    for rid, (share, count, n, reliable) in lifts.items():
        lift = None if share is None else round(share / baseline_share, 4)
        entry = {"share_recent": share, "count_recent": count, "share_prev": None, "count_prev": 0,
                 "lift": lift, "reliable": reliable, "example_threads": [], "ci95_recent": None}
        roles[rid] = {"name": rid.upper(), "n_recent": n,
                      "sectors": {"climate_energy": entry, "health": dict(entry, share_recent=0.0, count_recent=0,
                                                                          lift=0.0, reliable=False)}}
    base_entry = {"share_recent": baseline_share, "count_recent": 100, "share_prev": None, "count_prev": 0}
    return {"months": 12, "sectors": sectors, "baseline": {"n_recent": 1000, "sectors": {
        "climate_energy": base_entry, "health": base_entry}}, "roles": roles}


def _match(scores: dict[str, float], low: list[str] = ()) -> dict:
    ranked = sorted(scores, key=lambda r: -scores[r])
    roles = [{"role_id": r, "name": r.upper(), "rank": i, "rank_score": scores[r], "match_score": 0.5}
             for i, r in enumerate(ranked, start=1)]
    return {"scenario": "moderate", "roles": roles,
            "low_match": [{"role_id": r, "name": r.upper(), "rank": None, "rank_score": 0.2, "match_score": 0.1}
                          for r in low],
            "not_ranked": [], "unmatched": []}


def test_rerank_arithmetic_and_order():
    doc = _role_sdg({"a": (0.10, 20, 200, True),    # lift 1.0
                     "b": (0.30, 60, 200, True),    # lift 3.0
                     "c": (0.50, 5, 10, False)})    # lift 5.0 but too few posts
    out = rerank_for_goal(_match({"a": 0.80, "b": 0.70, "c": 0.60}), doc, "climate_energy")
    mult = {r["role_id"]: r["sdg_goal"]["multiplier"] for r in out["roles"]}
    assert mult["a"] == 1.0
    assert mult["b"] == pytest.approx(1 + GOAL_WEIGHT * 2.0)
    assert mult["c"] == 1.0  # not reliable: no boost
    fit = {r["role_id"]: r for r in out["by_goal_fit"]}
    assert fit["b"]["goal_fit_score"] == pytest.approx(0.70 * (1 + GOAL_WEIGHT * 2.0))
    assert [r["role_id"] for r in out["by_goal_fit"]] == ["b", "a", "c"]  # 0.91 > 0.80 > 0.60
    assert (fit["b"]["original_rank"], fit["b"]["goal_rank"]) == (2, 1)
    assert [r["role_id"] for r in out["roles"]] == ["a", "b", "c"]  # the original order is kept


def test_rerank_boost_is_capped_and_never_negative():
    doc = _role_sdg({"a": (0.90, 90, 100, True), "b": (0.01, 3, 300, True)}, baseline_share=0.05)
    out = rerank_for_goal(_match({"a": 0.5, "b": 0.5}), doc, "climate_energy")
    mult = {r["role_id"]: r["sdg_goal"]["multiplier"] for r in out["roles"]}
    assert mult["a"] == pytest.approx(1 + GOAL_WEIGHT * MAX_EXCESS)
    assert mult["b"] == 1.0  # under-represented: not lowered


def test_rerank_never_hides_roles_and_ties_keep_original_rank():
    doc = _role_sdg({"a": (0.1, 10, 100, True), "b": (0.1, 10, 100, True)})
    match = _match({"a": 0.7, "b": 0.7, "lowrole": 0.2}, low=["lowrole"])
    match["roles"] = [r for r in match["roles"] if r["role_id"] != "lowrole"]
    out = rerank_for_goal(match, doc, "climate_energy")
    assert [r["role_id"] for r in out["by_goal_fit"]] == [r["role_id"] for r in match["roles"]]
    assert [r["role_id"] for r in out["low_match"]] == ["lowrole"]
    assert out["low_match"][0]["sdg_goal"]["sentence"]  # a role missing from role_sdg still gets a sentence
    assert out["low_match"][0]["sdg_goal"]["multiplier"] == 1.0
    assert len(out["roles"]) + len(out["low_match"]) == 3


def test_rerank_sentence_uses_the_numbers():
    doc = _role_sdg({"a": (0.30, 60, 200, True)})
    out = rerank_for_goal(_match({"a": 0.8}), doc, "climate_energy")
    sentence = out["roles"][0]["sdg_goal"]["sentence"]
    assert sentence.startswith("30% of its posts are in Climate and clean energy (baseline 10%)")
    assert "3.0x the baseline" in sentence and "60 of 200 posts" in sentence
    assert "Too few" not in sentence
    rough = rerank_for_goal(_match({"a": 0.8}), _role_sdg({"a": (0.30, 3, 10, False)}), "climate_energy")
    assert "Too few posts" in rough["roles"][0]["sdg_goal"]["sentence"]


def test_rerank_keeps_the_input_unchanged_and_labels_the_formula():
    doc = _role_sdg({"a": (0.30, 60, 200, True)})
    match = _match({"a": 0.8})
    before = json.dumps(match, sort_keys=True)
    out = rerank_for_goal(match, doc, "climate_energy")
    assert json.dumps(match, sort_keys=True) == before
    assert "team judgement" in out["formula"]["basis"]
    assert out["formula"]["goal_weight"] == GOAL_WEIGHT
    assert out["sdg"] == ["7.2", "13.2"] and out["sector_name"] == "Climate and clean energy"


def test_rerank_unknown_goal_sector():
    with pytest.raises(ValueError, match="unknown goal sector"):
        rerank_for_goal(_match({"a": 0.5}), _role_sdg({"a": (0.1, 10, 100, True)}), "space_mining")


# ---------------------------------------------------------------- plan_sdg_summary

PLAN = {
    "target_role": "A",
    "steps": [{"skill": "SQL", "resource": {"cost": "free", "minutes": 120}},
              {"skill": "Spark", "resource": {"cost": "free", "minutes": 240}},
              {"skill": "dbt", "resource": None}],
    "totals": {"hours": 6.0, "steps": 3, "tasks": 8, "minutes": 360},
}


def _numbers_in(text: str) -> set[float]:
    return {float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)}


def test_plan_summary_without_goal():
    doc = _role_sdg({"a": (0.30, 60, 200, True)})
    doc["roles"]["a"]["outlook"] = {"trend_label": "Rising", "share_last12": 0.05, "share_prev12": 0.03}
    out = plan_sdg_summary(PLAN, "a", doc)
    assert len(out["lines"]) == 2
    assert out["lines"][0].startswith("SDG 4.4") and "2 job-listed skills in 6.0 hours" in out["lines"][0]
    assert out["lines"][1].startswith("SDG 8.5") and "Rising" in out["lines"][1]
    assert "5.0% of posts" in out["lines"][1] and "3.0% " in out["lines"][1]
    assert out["numbers"]["skills_added"] == 2 and out["numbers"]["hours"] == 6.0 and out["numbers"]["goal"] is None


def test_plan_summary_with_goal_uses_only_input_numbers():
    doc = _role_sdg({"a": (0.30, 60, 200, True)})
    doc["roles"]["a"]["outlook"] = {"trend_label": "Rising", "share_last12": 0.05, "share_prev12": 0.03}
    out = plan_sdg_summary(PLAN, "a", doc, goal_sector="climate_energy")
    goal = out["lines"][2]
    assert goal == ("30% of A posts in the last 12 months came from Climate and clean energy employers "
                    "(SDG 7.2 / 13.2), against 10% of all posts (60 of 200 posts).")
    allowed = {4.4, 8.5, 7.2, 13.2, 6.0, 2.0, 5.0, 3.0, 12.0, 30.0, 10.0, 60.0, 200.0, 0.0, 1.0}
    for line in out["lines"]:
        assert _numbers_in(line) <= allowed, line
    assert out["numbers"]["goal"]["share"] == 0.30 and out["numbers"]["goal"]["baseline_share"] == 0.10


def test_plan_summary_accepts_a_match_roles_result_and_a_role_name():
    doc = _role_sdg({"a": (0.30, 60, 200, True)})
    role_result = {"role_id": "a", "name": "Data A", "outlook": {"trend_label": "Falling", "share_last12": 0.02,
                                                                  "share_prev12": 0.04}}
    out = plan_sdg_summary(PLAN, role_result, doc, "climate_energy")
    assert "Falling" in out["lines"][1] and "Data A posts" in out["lines"][2]
    by_name = plan_sdg_summary(PLAN, "a", doc, "climate_energy")  # "A" is the display name of role id a
    assert "30% of A posts" in by_name["lines"][2]


def test_plan_summary_flags_rough_numbers_and_missing_roles():
    rough = plan_sdg_summary(PLAN, "a", _role_sdg({"a": (0.30, 3, 10, False)}), "climate_energy")
    assert "Too few posts" in rough["lines"][2]
    missing = plan_sdg_summary(PLAN, "zzz", _role_sdg({"a": (0.30, 60, 200, True)}), "climate_energy")
    assert "too few zzz posts" in missing["lines"][2] and missing["numbers"]["goal"] is None
    with pytest.raises(ValueError):
        plan_sdg_summary(PLAN, "a", _role_sdg({"a": (0.3, 60, 200, True)}), "nope")
