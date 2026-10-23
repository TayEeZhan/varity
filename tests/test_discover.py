"""Tests for engine.discover. Uses tiny synthetic threads in tmp_path, never data/raw."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import discover  # noqa: E402
from engine.discover import (  # noqa: E402
    DRAFT_STATUS,
    backtest_origin,
    discover as run_discover,
    draft_pattern,
    extract_terms,
    history,
    load_stoplist,
    normalise,
    scan_posts,
)

TAXONOMY = [
    {"skill": "Python", "category": "language", "synonyms": ["Python3"],
     "pattern": r"(?<![\w-])python3?(?!\w)", "case_sensitive": False},
    {"skill": "PostgreSQL", "category": "data", "synonyms": ["Postgres"],
     "pattern": r"(?<!\w)(?:postgres(?:ql)?|psql)(?!\w)", "case_sensitive": False},
    {"skill": "Kubernetes", "category": "cloud_devops", "synonyms": ["K8s"],
     "pattern": r"(?<![\w-])(?:kubernetes|k8s)(?!\w)", "case_sensitive": False},
    {"skill": "React", "category": "framework", "synonyms": ["ReactJS"],
     "pattern": r"(?<![\w.-])(?:react(?![ ]native)|reactjs)(?!\w)", "case_sensitive": False},
]
STOP = frozenset({"ceo", "usa"})


def terms(text, stoplist=STOP):
    return extract_terms(text, TAXONOMY, stoplist)


# --------------------------------------------------------------------------------------
# Term extraction
# --------------------------------------------------------------------------------------

def test_camel_case_terms_are_found():
    found = terms("Backend | We build with FastAPI and LangChain. Also ClickHouse.")
    assert {"fastapi", "langchain", "clickhouse"} <= found.keys()
    assert found["fastapi"].rules == {"camel_case"}
    assert found["langchain"].surface == "LangChain"


def test_plain_title_case_word_is_not_a_term():
    assert terms("Backend | We love Coffee and Teamwork in London.") == {}


def test_dotted_and_digit_terms_are_found():
    found = terms("Backend | Our stack is Next.js, Vue.js, gpt-4o and llama3 on k8s.")
    assert {"next.js", "vue.js", "gpt4o", "llama3"} <= found.keys()
    assert found["next.js"].rules >= {"tech_style"}
    assert found["llama3"].rules == {"tech_style"}


def test_simple_variants_share_one_key():
    assert normalise("nextjs") == normalise("Next.js") == "next.js"
    assert normalise("GPT-4o") == normalise("gpt4o") == "gpt4o"
    found = terms("Backend | We use nextjs. Others use Next.js.")
    assert list(found) == ["next.js"]


def test_dotnet_and_sharp_terms_are_found():
    found = terms("Backend | We write F# and .NET code, plus Foo++ tools.")
    assert {"f#", ".net", "foo++"} <= found.keys()


def test_short_letter_digit_tokens_are_not_terms():
    assert terms("Backend | Q3 plan, v2 launch, S3 bucket.") == {}


def test_all_caps_terms_respect_the_stoplist():
    found = terms("Backend | Our CEO in the USA wants an SRE and an OLAP expert.")
    assert "sre" in found and "olap" in found
    assert "ceo" not in found and "usa" not in found
    assert found["sre"].rules == {"all_caps"}
    # a long shout is not a 2 to 6 letter acronym
    assert "INTERESTING" not in {h.surface for h in terms("Backend | INTERESTING problems").values()}


def test_stoplist_file_is_read(tmp_path):
    path = tmp_path / "stop.txt"
    path.write_text("# a comment\nSaaS\n  CEO  # inline note\n\nNextJS\n", encoding="utf-8")
    assert load_stoplist(path) == frozenset({"saas", "ceo", "next.js"})
    assert load_stoplist(tmp_path / "missing.txt") == frozenset()


def test_list_context_finds_plain_lowercase_words():
    found = terms("Backend | Stack: Python, redis, Postgres and Celery")
    assert found["redis"].rules == {"list"}
    assert found["celery"].rules == {"list"}


def test_list_context_needs_two_known_skills():
    assert terms("Backend | Stack: Python, redis, memcached") == {}
    assert "redis" not in terms("Backend | We like redis. Python is fine.")


def test_list_context_works_with_slashes_and_brackets():
    found = terms("Backend | Python/Django/Postgres, (flask)")
    assert {"django", "flask"} <= found.keys()


def test_list_context_ignores_long_items_and_other_sentences():
    found = terms("Backend | Python, Postgres, we also run a very long item with redis. Cassandra is great")
    assert "redis" not in found and "cassandra" not in found


def test_header_cell_is_ignored_by_form_rules():
    found = terms("AcmeCorp | Dev | Remote\nWe use FastAPI.")
    assert "acmecorp" not in found
    assert "fastapi" in found


def test_known_skills_are_not_candidates():
    found = terms("Backend | ReactJS, k8s, PostgreSQL, Postgres, Python3, React, Kubernetes")
    assert found == {}


def test_known_lowercase_skill_name_in_a_list_is_dropped():
    found = terms("Backend | python, postgres, kubernetes, redis")
    assert set(found) == {"redis"}


def test_stoplisted_list_word_is_dropped():
    found = terms("Backend | Python, Postgres, usa, redis")
    assert set(found) == {"redis"}


def test_email_and_handle_pieces_are_not_terms():
    found = terms("Backend | Write to jobsTeam@AcmeCorp.com or @FooBar on Twitter.")
    assert "acmecorp.com" not in found and "foobar" not in found


# --------------------------------------------------------------------------------------
# Synthetic threads
# --------------------------------------------------------------------------------------

def _months(start, end):
    y, m = map(int, start.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def write_data(tmp_path, per_month, months):
    """Write raw threads and hn_threads.csv. per_month(month, i) returns the post texts of that month."""
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    lines = ["thread_id,month,created_at,title,url,n_top_level"]
    for i, month in enumerate(months):
        tid = 1000 + i
        posts = per_month(month, i)
        item = {"children": [{"type": "comment", "text": t, "author": "someone"} for t in posts]}
        (raw / f"{tid}.json").write_text(json.dumps(item), encoding="utf-8")
        lines.append(f"{tid},{month},{month}-01T00:00:00Z,Ask HN {month},"
                     f"https://news.ycombinator.com/item?id={tid},{len(posts)}")
    csv_path = tmp_path / "threads.csv"
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return raw, csv_path


N = 20  # posts per month
MONTHS = _months("2021-01", "2024-06")  # 42 months
ORIGIN = "2023-06"  # last window 2022-07..2023-06, prior 2021-07..2022-06


def posts_for(month, i):
    """20 posts a month. Counts per month of each term are set below."""
    rise = 4 if "2022-07" <= month <= "2023-06" else (8 if month > "2023-06" else (1 if month >= "2021-07" else 0))
    new = 3 if month >= "2022-07" else 0
    flat = 3 if month >= "2021-01" else 0
    fall = 4 if "2022-07" <= month <= "2023-06" else 0
    posts = []
    for j in range(rise):
        posts.append(f"Co{j} | Dev | Remote\nWe use AlphaTool and Python daily. Contact Jane Doe jane@example.com")
    for j in range(new):
        posts.append(f"Co{j} | Dev\nOur stack has BetaKit.")
    for j in range(flat):
        posts.append(f"Co{j} | Dev\nWe also use GammaDB.")
    for j in range(fall):
        posts.append(f"Co{j} | Dev\nWe use DeltaKit now.")
    while len(posts) < N:
        posts.append("Filler | Java shop, SECRETSENTENCE about nothing")
    return posts[:N]


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("disc")
    raw, csv_path = write_data(tmp, posts_for, MONTHS)
    return raw, csv_path, scan_posts(raw, csv_path, TAXONOMY, STOP)


def by_key(result):
    return {c["key"]: c for c in result["candidates"]}


# --------------------------------------------------------------------------------------
# Counting, growth, ranking
# --------------------------------------------------------------------------------------

def test_post_counts_once_even_when_term_repeats(tmp_path):
    """3 posts a month each say AlphaTool three times: 36 posts in 12 months, not 108 mentions."""
    def per_month(month, i):
        posts = ["Co | Dev\nAlphaTool AlphaTool AlphaTool and alphatool again."] * 3
        return posts + [f"Filler | Java shop {k}" for k in range(N - 3)]

    raw, csv_path = write_data(tmp_path, per_month, _months("2022-01", "2023-12"))
    res = run_discover(raw, csv_path, TAXONOMY, as_of="2023-12")
    assert by_key(res)["alphatool"]["mentions_last"] == 36


def test_growth_and_new_term_ranking(data):
    raw, csv_path, scan = data
    res = run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan)
    cands = by_key(res)
    # both new terms rank above the growing one; DeltaKit has more posts than BetaKit
    assert [c["key"] for c in res["candidates"]] == ["deltakit", "betakit", "alphatool", "gammadb"]
    alpha, beta, gamma = cands["alphatool"], cands["betakit"], cands["gammadb"]
    n_last, n_prior = 12 * N, 12 * N
    assert alpha["mentions_last"] == 48 and alpha["mentions_prior"] == 12
    assert alpha["growth"] == pytest.approx((48 / n_last) / (12 / n_prior), abs=0.01)
    assert alpha["kind"] == "growth" and alpha["new_since"] is None
    # absent before: the prior share is replaced by 1 / n_prior_posts
    assert beta["mentions_prior"] == 0 and beta["kind"] == "new"
    assert beta["new_since"] == "2022-07"
    assert beta["growth"] == pytest.approx((36 / n_last) / (1 / n_prior), abs=0.01)
    assert beta["growth"] > alpha["growth"]
    assert gamma["growth"] == pytest.approx(1.0, abs=0.01)
    assert alpha["first_seen"] == "2021-07" and gamma["first_seen"] == "2021-01"


def test_rank_is_by_score_with_list_weight(data):
    raw, csv_path, scan = data
    res = run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan)
    scores = [c["score"] for c in res["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert [c["rank"] for c in res["candidates"]] == list(range(1, len(scores) + 1))
    c = res["candidates"][0]
    # no list context here, so the weight is 0.5
    assert c["evidence"]["list_fraction"] == 0.0
    assert c["score"] == pytest.approx(c["growth"] * 0.5, abs=0.01)


def test_list_context_raises_the_score(tmp_path):
    """Same growth, but one term sits in skill lists: it must rank above the one that does not."""
    def per_month(month, i):
        posts = []
        n = 3 if month >= "2022-07" else 1
        for _ in range(n):
            posts.append("Co | Dev\nStack: Python, Postgres, fastmq")
            posts.append("Co | Dev\nWe use TwinTool in prose.")
        return posts + [f"Filler | Java shop {k}" for k in range(N - 2 * n)]

    raw, csv_path = write_data(tmp_path, per_month, _months("2021-07", "2023-06"))
    res = run_discover(raw, csv_path, TAXONOMY, as_of="2023-06")
    keys = [c["key"] for c in res["candidates"]]
    assert keys == ["fastmq", "twintool"]
    fast, twin = res["candidates"]
    assert fast["growth"] == twin["growth"]
    assert fast["evidence"]["list_fraction"] == 1.0 and fast["score"] == 2 * twin["score"]


def _flat_term(tmp_path, per_month_count):
    def per_month(month, i):
        posts = ["Co | Dev\nWe use AlphaTool."] * per_month_count(month) if month >= "2022-07" else []
        return posts + [f"Filler | Java shop {k}" for k in range(N - len(posts))]

    return write_data(tmp_path, per_month, _months("2021-07", "2023-06"))


def test_threshold_of_30_posts_in_the_last_12_months(tmp_path):
    raw, csv_path = _flat_term(tmp_path / "a", lambda m: 2)  # 24 posts
    assert run_discover(raw, csv_path, TAXONOMY, as_of="2023-06")["candidates"] == []
    raw, csv_path = _flat_term(tmp_path / "b", lambda m: 3 if m >= "2023-01" else 2)  # 18 + 12 = 30
    got = run_discover(raw, csv_path, TAXONOMY, as_of="2023-06")["candidates"]
    assert [c["mentions_last"] for c in got] == [30]  # exactly 30 is kept


def test_min_mentions_can_be_lowered(tmp_path):
    raw, csv_path = _flat_term(tmp_path, lambda m: 2)  # 24 posts in the last 12 months
    assert run_discover(raw, csv_path, TAXONOMY, as_of="2023-06")["candidates"] == []
    got = run_discover(raw, csv_path, TAXONOMY, as_of="2023-06", min_mentions=20)["candidates"]
    assert [c["key"] for c in got] == ["alphatool"]


def test_ordinary_prose_word_is_filtered_by_signal_ratio(tmp_path):
    """'Gadgetry' is camel-free prose. 'GadgetKit' is a tool. The word seen mostly in plain prose is dropped."""
    def per_month(month, i):
        posts = ["Co | Dev\nStack: Python, Postgres, widget"] * 1
        posts += ["Co | Dev\nI like a widget here and a widget there."] * 4  # prose uses of the same word
        return posts + [f"Filler | Java shop {k}" for k in range(N - len(posts))]

    raw, csv_path = write_data(tmp_path, per_month, _months("2021-07", "2023-06"))
    res = run_discover(raw, csv_path, TAXONOMY, as_of="2023-06")
    assert res["candidates"] == []  # 1 of 5 posts is list style: 20% is under 50%


def test_trend_label_uses_existing_welch_test(data):
    raw, csv_path, scan = data
    cands = by_key(run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan))
    assert cands["alphatool"]["label"] == "Rising"
    assert cands["alphatool"]["p_value"] is not None
    assert cands["gammadb"]["label"] == "No clear change"


def test_co_occurring_skills_and_category(data):
    raw, csv_path, scan = data
    alpha = by_key(run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan))["alphatool"]
    top = alpha["co_occurring_skills"]
    assert top[0]["skill"] == "Python" and top[0]["posts"] == 48
    assert top[0]["lift"] == pytest.approx(5.0)  # all 48 posts have Python; 48 of 240 posts overall
    assert alpha["suggested_category"] == "language"
    assert len(top) <= 3
    assert by_key(run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan))["betakit"]["co_occurring_skills"] == []


def test_examples_are_two_thread_urls_only(data):
    raw, csv_path, scan = data
    alpha = by_key(run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan))["alphatool"]
    ex = alpha["examples"]
    assert len(ex) == 2 and ex[0]["thread_url"] != ex[1]["thread_url"]
    for e in ex:
        assert set(e) == {"month", "thread_url"}
        assert re.fullmatch(r"https://news\.ycombinator\.com/item\?id=\d+", e["thread_url"])


def test_no_post_text_names_or_emails_in_output(data):
    raw, csv_path, scan = data
    res = run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan)
    text = json.dumps(res)
    for forbidden in ("Jane", "jane@", "example.com", "SECRETSENTENCE", "someone", "Filler", "Remote", "daily"):
        assert forbidden not in text
    assert not re.search(r"\S+@\S+\.\S+", text)


def test_as_of_uses_no_later_data(data, tmp_path):
    """Cut at ORIGIN, the result is the same as on a data set that ends at ORIGIN."""
    raw, csv_path, scan = data
    full = run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan)
    short_months = [m for m in MONTHS if m <= ORIGIN]
    raw2, csv2 = write_data(tmp_path, posts_for, short_months)
    cut = run_discover(raw2, csv2, TAXONOMY)
    assert full["as_of"] == cut["as_of"] == ORIGIN
    assert full["candidates"] == cut["candidates"]
    # a term that exists only after the origin is invisible at the origin
    assert "alphatool" in by_key(run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan))


def test_future_only_term_is_not_flagged_before_it_exists(tmp_path):
    def per_month(month, i):
        posts = ["Co | Dev\nWe use FutureKit."] * 4 if month >= "2023-07" else []
        return posts + [f"Filler | Java shop {k}" for k in range(N - len(posts))]

    raw, csv_path = write_data(tmp_path, per_month, _months("2021-01", "2024-06"))
    assert run_discover(raw, csv_path, TAXONOMY, as_of="2023-06")["candidates"] == []
    assert [c["key"] for c in run_discover(raw, csv_path, TAXONOMY, as_of="2024-06")["candidates"]] == ["futurekit"]


def test_reading_threads_in_several_processes_gives_the_same_result(data):
    raw, csv_path, scan = data
    parallel = scan_posts(raw, csv_path, TAXONOMY, STOP, workers=2)
    assert run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=parallel) ==         run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan)


def test_as_of_and_window_are_validated(data):
    raw, csv_path, scan = data
    with pytest.raises(ValueError):
        run_discover(raw, csv_path, TAXONOMY, as_of="2023-6", scan=scan)
    with pytest.raises(ValueError):
        run_discover(raw, csv_path, TAXONOMY, as_of="2021-05", scan=scan)  # under 24 months of data
    with pytest.raises(ValueError):
        run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, window=6, scan=scan)


# --------------------------------------------------------------------------------------
# Draft pattern and history
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("term", ["FastAPI", "Next.js", "gpt-4o", "llama3", "SRE", "F#", ".NET", "redis", "ClickHouse"])
def test_draft_pattern_compiles_and_matches_its_own_term(term):
    spec = draft_pattern(term)
    assert spec["status"] == DRAFT_STATUS == "draft, needs review and tests"
    regex = re.compile(spec["pattern"], 0 if spec["case_sensitive"] else re.IGNORECASE)
    assert regex.search(f"We use {term} here.")
    assert regex.search(f"{term}")
    assert regex.search(f"Python, {term}.")
    assert not regex.search(f"We use not{term.lstrip('.')}x")


def test_draft_pattern_case_rule_and_variants():
    sre = draft_pattern("SRE")
    assert sre["case_sensitive"] is True and re.search(sre["pattern"], "an SRE role")
    assert not re.search(sre["pattern"], "a sre role")
    nxt = re.compile(draft_pattern("Next.js")["pattern"], re.IGNORECASE)
    assert all(nxt.search(f"use {v} now") for v in ("Next.js", "nextjs", "NextJS", "next js"))
    gpt = re.compile(draft_pattern("gpt4o")["pattern"], re.IGNORECASE)
    assert gpt.search("GPT-4o") and gpt.search("gpt4o") and not gpt.search("gpt4omni")
    assert draft_pattern("FastAPI")["case_sensitive"] is False
    with pytest.raises(ValueError):
        draft_pattern("  ")


def test_history_gives_full_series_from_raw_posts(data):
    raw, csv_path, _ = data
    rows = history("AlphaTool", raw, csv_path)
    assert [r["month"] for r in rows] == MONTHS
    assert all(r["n_posts"] == N for r in rows)
    first = next(r for r in rows if r["mentions"])
    assert first["month"] == "2021-07"  # backfilled to the first month it was ever used
    assert rows[0]["share"] == 0.0
    assert [r["mentions"] for r in rows if r["month"] == "2023-07"] == [8]
    assert [r["share"] for r in rows if r["month"] == "2023-07"] == [8 / N]


def test_history_equals_what_demand_would_count(data):
    """The approved skill's history must equal the count engine.demand makes with the same pattern."""
    from engine.demand import build_demand

    raw, csv_path, _ = data
    spec = draft_pattern("AlphaTool")
    tax = TAXONOMY + [{"skill": "AlphaTool", "pattern": spec["pattern"], "case_sensitive": spec["case_sensitive"]}]
    tax_path = csv_path.parent / "tax.json"
    tax_path.write_text(json.dumps(tax), encoding="utf-8")
    rows = [r for r in build_demand(csv_path, raw, None, tax_path) if r["skill"] == "AlphaTool"]
    hist = history("AlphaTool", raw, csv_path)
    assert [(r["month"], r["mentions"], r["n_posts"]) for r in rows] == [
        (h["month"], h["mentions"], h["n_posts"]) for h in hist]


# --------------------------------------------------------------------------------------
# Backtest and report
# --------------------------------------------------------------------------------------

def test_backtest_origin_counts_hits_without_using_the_future_to_pick(data):
    raw, csv_path, scan = data
    res = backtest_origin(scan, ORIGIN, top_n=15)
    by_term = {r["term"]: r for r in res["top"]}
    assert res["as_of"] == ORIGIN and res["after_months"] == ["2023-07", "2024-06"]
    assert by_term["AlphaTool"]["rose"] is True  # 4 a month -> 8 a month
    assert by_term["BetaKit"]["rose"] is False  # 3 a month -> 3 a month: equal is not above
    assert by_term["DeltaKit"]["rose"] is False  # gone after the origin
    assert res["hits"] == sum(r["rose"] for r in res["top"])
    assert res["precision_top"] == pytest.approx(res["hits"] / res["top_n"], abs=0.01)
    # the same candidates are picked as discover() picks at the origin
    picked = [c["term"] for c in run_discover(raw, csv_path, TAXONOMY, as_of=ORIGIN, scan=scan)["candidates"]]
    assert [r["term"] for r in res["top"]] == picked[:15]


def test_backtest_needs_twelve_months_after_origin(data):
    _, _, scan = data
    with pytest.raises(ValueError):
        backtest_origin(scan, "2024-01")


def test_main_writes_the_json_file(data, tmp_path, capsys):
    raw, csv_path, _ = data
    out = tmp_path / "out" / "skill_candidates.json"
    assert discover.main(["--raw-dir", str(raw), "--threads-csv", str(csv_path), "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert {"generated_at", "as_of", "window", "rules", "candidates", "backtest", "status"} <= doc.keys()
    assert doc["as_of"] == MONTHS[-1] and doc["window"] == 12
    assert doc["backtest"]["main"]["as_of"] == "2023-06"
    assert "taxonomy.json" in doc["status"]
    assert doc["candidates"] and doc["candidates"][0]["draft_pattern"]["status"] == DRAFT_STATUS
    assert doc["backfill_demo"]["months"] == MONTHS
    assert "Runtime" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# App: the radar table at the bottom of the Method tab
# --------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not (ROOT / "data" / "skill_candidates.json").exists()
                    or not (ROOT / "data" / "skill_scores.json").exists(),
                    reason="data/skill_candidates.json or data/skill_scores.json not generated yet")
def test_method_tab_shows_the_candidate_radar():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    headers = [h.value for h in at.header]
    assert headers[-1] == "Candidate new skills (not yet in Verity; need human review)" or \
        "Candidate new skills (not yet in Verity; need human review)" in headers
    doc = json.loads((ROOT / "data" / "skill_candidates.json").read_text(encoding="utf-8"))
    radar = next(df for df in at.dataframe if "Term" in df.value.columns and "Source 1" in df.value.columns)
    assert list(radar.value["Term"]) == [c["term"] for c in doc["candidates"][:15]]
    assert len(radar.value) <= 15
    assert all(str(u).startswith("https://news.ycombinator.com/item?id=") for u in radar.value["Source 1"].dropna())
