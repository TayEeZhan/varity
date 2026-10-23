"""Tests for engine/my_jobs.py. No test touches the network: sessions are fakes."""
import csv
import re
import urllib.robotparser
from pathlib import Path

import pytest

from engine import my_jobs
from engine.my_jobs import (
    ChallengeDetected,
    FetchFailed,
    Hiredly,
    JobStore,
    Listing,
    PoliteFetcher,
    RobotsDisallowed,
    RobotsRules,
    aggregate,
    append_snapshot,
    collect_site,
    compare_with_hn,
    is_challenge,
    plain,
    strip_pii,
)
from engine.tagging import load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "my_jobs"
TAXONOMY = load_taxonomy()
ROLES = my_jobs.load_roles()


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- fakes
class FakeResponse:
    def __init__(self, status=200, text="", headers=None, url=""):
        self.status_code = status
        self.text = text
        self.headers = headers if headers is not None else {"content-type": "text/html; charset=utf-8"}
        self.url = url
        self.encoding = "utf-8"


class FakeSession:
    """Answers by URL. `routes` maps a URL to a response, a list of responses (used in order) or a callable."""

    def __init__(self, routes):
        self.routes = routes
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None, allow_redirects=True):
        self.calls.append((url, timeout))
        route = self.routes.get(url)
        if route is None:
            return FakeResponse(404, "", url=url)
        if isinstance(route, list):
            route = route.pop(0) if len(route) > 1 else route[0]
        if callable(route):
            route = route(url)
        route.url = url
        return route


class FakeTime:
    """A clock that only moves when sleep is called."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_fetcher(routes, tmp_path, ft=None):
    ft = ft or FakeTime()
    session = FakeSession(routes)
    fetcher = PoliteFetcher(
        session=session, sleep=ft.sleep, clock=ft.clock, raw_dir=tmp_path / "raw", today="2026-10-23"
    )
    return fetcher, session, ft


OPEN_ROBOTS = FakeResponse(200, "User-agent: *\nAllow: /\n")


# ---------------------------------------------------------------- parsing
def test_hiredly_parse_keeps_only_listing_fields():
    listings = Hiredly.parse(fixture("hiredly_page.html"))
    assert [x.listing_id for x in listings] == ["aaaa-1111", "bbbb-2222", "cccc-3333"]  # row without id is dropped
    first = listings[0]
    assert first.title == "Senior Backend Engineer (Python)"
    assert first.posted == "2026-10-20"
    assert first.location == "Kuala Lumpur"
    assert "PostgreSQL" in first.teaser and "Docker" in first.teaser  # summary plus skill chips
    assert listings[2].posted is None
    dumped = repr(listings)
    assert "Fixture Co" not in dumped and "fixture.example" not in dumped  # employer fields are never read


def test_hiredly_parse_survives_bad_pages():
    assert Hiredly.parse("") == []
    assert Hiredly.parse("<html>no data</html>") == []
    assert Hiredly.parse('<script id="__NEXT_DATA__" type="application/json">{broken</script>') == []
    assert Hiredly.parse('<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script>') == []


def test_jobstore_parse_reads_cards_and_truncates_description():
    listings = JobStore.parse(fixture("jobstore_page.html"))
    assert [x.listing_id for x in listings] == ["l111", "l222", "l333"]
    first = listings[0]
    assert first.title == "Software Engineer"
    assert first.location == "Kuala Lumpur, Malaysia"
    assert first.posted is None
    assert "React" in first.teaser and "TypeScript" in first.teaser
    assert listings[2].teaser == ""  # broken JSON gives an empty teaser, not a crash
    assert "Fixture Company" not in repr(listings)  # company name is never read


def test_urls_follow_each_sites_own_pattern():
    assert Hiredly.build_url("AI engineer", 1) == "https://my.hiredly.com/jobs-in-ai-engineer"
    assert Hiredly.build_url("AI engineer", 3) == "https://my.hiredly.com/jobs-in-ai-engineer?page=3"
    assert JobStore.build_url("data scientist", 1) == "https://www.jobstore.com/my/jobs/q-data-scientist.html"
    assert JobStore.build_url("data scientist", 2) == "https://www.jobstore.com/my/jobs/q-data-scientist.html?page=2"


# ---------------------------------------------------------------- PII
@pytest.mark.parametrize(
    "raw",
    [
        "Mail hr@example.com today",
        "Call +60 12-345 6789 now",
        "Phone 012-345 6789",
        "Contact: Ms Tan Wei Ling for details",
        "Attn - John Smith",
        "PIC: Aina",
        "Send your CV to Ms Lim at the office",
        "Chat https://wa.me/60123456789 anytime",
    ],
)
def test_strip_pii_removes_personal_data(raw):
    cleaned = strip_pii(raw)
    for secret in ("hr@example.com", "345 6789", "Tan", "John", "Aina", "Lim", "wa.me", "60123456789"):
        assert secret not in cleaned


def test_strip_pii_keeps_normal_text():
    text = "We call APIs daily and use Python 3.12 with 5 years of experience in 2026."
    assert strip_pii(text) == text


def test_plain_strips_html_and_pii_in_one_line():
    out = plain("<p>React and <b>Docker</b></p><p>Email hr@example.com</p>")
    assert "\n" not in out and "hr@example.com" not in out
    assert "React" in out and "Docker" in out


def test_parsed_teasers_contain_no_pii():
    for listing in Hiredly.parse(fixture("hiredly_page.html")) + JobStore.parse(fixture("jobstore_page.html")):
        blob = f"{listing.title} {listing.teaser} {listing.location}"
        assert "@" not in blob and "345 6789" not in blob and "Example Name" not in blob and "Example Person" not in blob


# ---------------------------------------------------------------- robots
def test_robots_longest_match_wins_and_wildcards_work():
    rules = RobotsRules.parse(fixture("robots_wildcards.txt"), token="someoneelse")
    assert rules.group == "*"
    assert rules.allowed("/jobs?keywords=python")  # Allow: *?keywords beats Disallow: *?
    assert not rules.allowed("/jobs?page=2")  # Disallow: *?
    assert not rules.allowed("/en/job/12345")  # Disallow: */job/
    assert not rules.allowed("/api/jobsearch/x")
    assert rules.allowed("/public")  # Allow: /public$
    assert rules.allowed("/jobs")  # no rule matches
    assert rules.deciding_rule("/jobs?page=2") == "Disallow: *?"


def test_robots_prefers_group_that_names_us_and_ignores_other_bots():
    ours = RobotsRules.parse(fixture("robots_wildcards.txt"))  # token "verity"
    assert ours.group == "verity"
    assert not ours.allowed("/secret/a")
    assert ours.allowed("/jobs?page=2")  # the "*" group does not apply to us


def test_robots_no_applicable_group_means_allowed():
    rules = RobotsRules.parse("User-agent: Googlebot\nAllow: /\n")
    assert rules.group is None
    assert rules.allowed("/anything?x=1")
    assert RobotsRules.parse("").allowed("/x")


def test_robots_tie_goes_to_allow_and_empty_disallow_is_ignored():
    rules = RobotsRules.parse("User-agent: *\nDisallow: /a\nAllow: /a\nDisallow:\n")
    assert rules.allowed("/a/b")


def test_robots_matcher_agrees_with_stdlib_on_plain_rules():
    text = "User-agent: *\nDisallow: /private/\nAllow: /private/ok\n"
    stdlib = urllib.robotparser.RobotFileParser()
    stdlib.parse(text.splitlines())
    ours = RobotsRules.parse(text)
    for path in ("/", "/private/x", "/public", "/private/"):
        assert ours.allowed(path) == stdlib.can_fetch("Verity", path), path


def test_stdlib_ignores_wildcards_which_is_why_we_have_our_own():
    text = "User-agent: *\nDisallow: *?\n"
    stdlib = urllib.robotparser.RobotFileParser()
    stdlib.parse(text.splitlines())
    assert stdlib.can_fetch("Verity", "/jobs?page=2")  # stdlib wrongly allows it
    assert not RobotsRules.parse(text).allowed("/jobs?page=2")


def test_fetcher_skips_a_disallowed_path_without_requesting_it(tmp_path):
    robots = FakeResponse(200, "User-agent: *\nDisallow: /secret/\n")
    fetcher, session, _ = make_fetcher({"https://site.test/robots.txt": robots}, tmp_path)
    with pytest.raises(RobotsDisallowed):
        fetcher.get("https://site.test/secret/page")
    assert [url for url, _ in session.calls] == ["https://site.test/robots.txt"]


def test_missing_robots_file_means_allowed_but_blocked_robots_means_skip(tmp_path):
    page = FakeResponse(200, "<html><title>ok</title></html>")
    fetcher, _, _ = make_fetcher({"https://a.test/x": page}, tmp_path)  # robots.txt gives 404
    assert fetcher.get("https://a.test/x").status == 200
    fetcher2, session2, _ = make_fetcher({"https://b.test/robots.txt": FakeResponse(403, "no")}, tmp_path)
    with pytest.raises(ChallengeDetected):
        fetcher2.get("https://b.test/x")
    assert all(url.endswith("robots.txt") for url, _ in session2.calls)


# ---------------------------------------------------------------- challenge detection
def test_challenge_header_status_and_title_markers():
    assert is_challenge(403, {"Cf-Mitigated": "challenge"}, "<title>Just a moment...</title>")
    assert is_challenge(200, {"cf-mitigated": "challenge"}, "")
    assert is_challenge(403, {}, "forbidden")
    assert is_challenge(429, {}, "slow down")
    assert is_challenge(200, {}, "<html><title>Just a moment...</title></html>")
    assert is_challenge(200, {}, "<html><title>Attention Required! | Cloudflare</title></html>")
    assert is_challenge(200, {}, "<script>window._cf_chl_opt={}</script>")


def test_normal_cloudflare_page_is_not_a_challenge():
    page = '<html><title>Jobs</title><script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script></html>'
    assert not is_challenge(200, {"server": "cloudflare"}, page)
    assert not is_challenge(200, {}, fixture("hiredly_page.html"))
    assert not is_challenge(200, {}, fixture("jobstore_page.html"))


def test_challenge_stops_the_whole_site_and_nothing_is_retried(tmp_path):
    challenge = FakeResponse(403, "<title>Just a moment...</title>", {"cf-mitigated": "challenge"})
    routes = {
        "https://my.hiredly.com/robots.txt": OPEN_ROBOTS,
        "https://my.hiredly.com/jobs-in-software-engineer": challenge,
    }
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    result = collect_site(fetcher, Hiredly, queries=("software engineer", "developer"), max_pages=3)
    assert result.listings == {}
    assert result.stopped.startswith("ChallengeDetected")
    assert len(session.calls) == 2  # robots.txt and one page. No retry, no second query.
    with pytest.raises(ChallengeDetected):  # the host stays blocked for the run
        fetcher.get("https://my.hiredly.com/jobs-in-developer")
    assert len(session.calls) == 2
    assert not (tmp_path / "raw").exists()  # nothing saved from a challenge page


# ---------------------------------------------------------------- pacing, retries, timeout
def test_pacing_waits_three_seconds_between_requests_to_one_host(tmp_path):
    routes = {"https://s.test/robots.txt": OPEN_ROBOTS, "https://s.test/a": FakeResponse(200, "a"), "https://s.test/b": FakeResponse(200, "b")}
    fetcher, session, ft = make_fetcher(routes, tmp_path)
    fetcher.get("https://s.test/a")
    fetcher.get("https://s.test/b")
    assert len(session.calls) == 3  # robots, a, b
    assert ft.sleeps == [3.0, 3.0]  # nothing else advanced the clock, so each gap is a full 3 s


def test_pacing_counts_time_already_spent_and_is_per_host(tmp_path):
    routes = {
        "https://one.test/robots.txt": OPEN_ROBOTS,
        "https://two.test/robots.txt": OPEN_ROBOTS,
        "https://one.test/a": FakeResponse(200, "a"),
        "https://two.test/a": FakeResponse(200, "a"),
    }
    ft = FakeTime()
    fetcher, _, _ = make_fetcher(routes, tmp_path, ft)
    fetcher.get("https://one.test/a")
    assert ft.sleeps == [3.0]  # robots.txt then the page: one gap on host one
    fetcher.get("https://two.test/a")  # a new host has its own clock: its first request does not wait
    assert ft.sleeps == [3.0, 3.0]  # only the gap between its robots.txt and its page
    ft.now += 10  # a long gap needs no extra wait
    before = len(ft.sleeps)
    fetcher._pace("one.test")
    assert len(ft.sleeps) == before


def test_user_agent_and_timeout_are_set(tmp_path):
    routes = {"https://s.test/robots.txt": OPEN_ROBOTS, "https://s.test/a": FakeResponse(200, "a")}
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    fetcher.get("https://s.test/a")
    assert session.headers["User-Agent"] == "Verity hackathon project (XMUM SDC 2026)"
    assert all(timeout == 30 for _, timeout in session.calls)


def test_server_errors_retry_with_growing_backoff_then_succeed(tmp_path):
    routes = {
        "https://s.test/robots.txt": OPEN_ROBOTS,
        "https://s.test/a": [FakeResponse(503, "x"), FakeResponse(502, "x"), FakeResponse(200, "fine")],
    }
    fetcher, session, ft = make_fetcher(routes, tmp_path)
    assert fetcher.get("https://s.test/a").text == "fine"
    backoffs = [s for s in ft.sleeps if s >= 5.0]
    assert backoffs == [5.0, 10.0]
    assert len(session.calls) == 4  # robots + 3 tries


def test_retries_give_up_after_four_tries(tmp_path):
    routes = {"https://s.test/robots.txt": OPEN_ROBOTS, "https://s.test/a": FakeResponse(500, "x")}
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    with pytest.raises(FetchFailed):
        fetcher.get("https://s.test/a")
    assert len(session.calls) == 1 + 4


def test_network_error_is_retried(tmp_path):
    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("boom")
        return FakeResponse(200, "ok")

    routes = {"https://s.test/robots.txt": OPEN_ROBOTS, "https://s.test/a": flaky}
    fetcher, _, _ = make_fetcher(routes, tmp_path)
    assert fetcher.get("https://s.test/a").text == "ok"


def test_raw_response_is_saved_under_site_and_date(tmp_path):
    routes = {"https://my.hiredly.com/robots.txt": OPEN_ROBOTS, "https://my.hiredly.com/x": FakeResponse(200, "<html>raw</html>")}
    fetcher, _, _ = make_fetcher(routes, tmp_path)
    fetcher.get("https://my.hiredly.com/x", raw_name="page1")
    assert (tmp_path / "raw" / "my-hiredly-com" / "2026-10-23" / "page1.html").read_text(encoding="utf-8") == "<html>raw</html>"


# ---------------------------------------------------------------- collect_site
def test_collect_site_dedups_across_queries_and_stops_paging_on_repeat(tmp_path):
    page = FakeResponse(200, fixture("hiredly_page.html"))
    routes = {
        "https://my.hiredly.com/robots.txt": OPEN_ROBOTS,
        "https://my.hiredly.com/jobs-in-software-engineer": page,
        "https://my.hiredly.com/jobs-in-software-engineer?page=2": page,  # same rows again: stop paging
        "https://my.hiredly.com/jobs-in-developer": FakeResponse(200, fixture("hiredly_page.html")),
    }
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    result = collect_site(fetcher, Hiredly, queries=("software engineer", "developer"), max_pages=3)
    assert result.stopped is None
    assert len(result.listings) == 3  # the same 3 listings seen in several queries count once
    fetched = [url for url, _ in session.calls]
    assert "https://my.hiredly.com/jobs-in-software-engineer?page=3" not in fetched
    assert "https://my.hiredly.com/jobs-in-developer?page=2" not in fetched  # nothing new on page 1 of "developer"


def test_collect_site_respects_page_limit(tmp_path):
    def page_n(url):
        n = int(url.rsplit("=", 1)[-1]) if "page=" in url else 1
        row = f'{{"id":"id{n}","title":"Developer {n}","gptSummary":"x","skills":[]}}'
        return FakeResponse(200, f'<script id="__NEXT_DATA__" type="application/json">{{"props":{{"pageProps":{{"jobs":[{row}]}}}}}}</script>')

    routes = {"https://my.hiredly.com/robots.txt": OPEN_ROBOTS}
    for n in range(1, 6):
        routes[Hiredly.build_url("developer", n)] = page_n
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    result = collect_site(fetcher, Hiredly, queries=("developer",), max_pages=3)
    assert len(result.listings) == 3
    assert result.pages_fetched == 3
    assert not any("page=4" in url for url, _ in session.calls)


# ---------------------------------------------------------------- aggregation
def L(i, title, teaser="", site="hiredly"):
    return Listing(site=site, listing_id=str(i), title=title, posted=None, location=None, teaser=teaser)


def test_aggregate_counts_each_skill_once_per_listing_and_computes_share():
    listings = [
        L(1, "Backend Engineer", "Python Python Python and PostgreSQL"),
        L(2, "Data Engineer", "Python with Airflow and Spark"),
        L(3, "Sales Executive", "Sell things"),
        L(4, "Frontend Developer", "React and TypeScript"),
    ]
    skills, roles = aggregate(listings, TAXONOMY, ROLES, "2026-10-23", "hiredly")
    by_skill = {r["skill"]: r for r in skills}
    assert by_skill["Python"]["mentions"] == 2  # a listing counts once, however often the word repeats
    assert by_skill["Python"]["n_listings"] == 4
    assert by_skill["Python"]["share"] == 0.5
    assert by_skill["PostgreSQL"]["mentions"] == 1
    assert "SQL" not in by_skill  # PostgreSQL does not count as SQL (tagging rule)
    assert all(r["snapshot_date"] == "2026-10-23" and r["site"] == "hiredly" for r in skills)
    assert skills == sorted(skills, key=lambda r: (-r["mentions"], r["skill"]))


def test_aggregate_roles_use_titles_only_and_list_every_role():
    listings = [
        L(1, "Senior Backend Engineer", "we are a data scientist shop"),  # teaser must not create a role
        L(2, "Data Scientist"),
        L(3, "Full Stack Developer"),
        L(4, "DevOps Engineer"),
        L(5, "Sales Executive"),
    ]
    _, roles = aggregate(listings, TAXONOMY, ROLES, "2026-10-23", "jobstore")
    by_role = {r["role_id"]: r for r in roles}
    assert set(by_role) == {r["id"] for r in ROLES}  # all 9 roles, zeros included
    assert by_role["backend_engineer"]["n"] == 1
    assert by_role["data_scientist"]["n"] == 1
    assert by_role["fullstack_developer"]["n"] == 1
    assert by_role["platform_devops_engineer"]["n"] == 1
    assert by_role["ml_engineer"]["n"] == 0
    assert by_role["data_scientist"]["share"] == 0.2


def test_aggregate_empty_input_gives_no_skill_rows_and_zero_roles():
    skills, roles = aggregate([], TAXONOMY, ROLES, "2026-10-23", "hiredly")
    assert skills == []
    assert all(r["n"] == 0 and r["share"] == 0.0 for r in roles)


# ---------------------------------------------------------------- snapshot files
def test_append_snapshot_appends_a_new_date_and_replaces_a_same_day_rerun(tmp_path):
    path = tmp_path / "snap.csv"
    row = lambda d, s, m: {"snapshot_date": d, "site": s, "skill": "Python", "mentions": m, "n_listings": 10, "share": m / 10}
    append_snapshot(path, my_jobs.SKILLS_COLUMNS, [row("2026-10-23", "hiredly", 3)], "2026-10-23", "hiredly")
    append_snapshot(path, my_jobs.SKILLS_COLUMNS, [row("2026-10-23", "jobstore", 4)], "2026-10-23", "jobstore")
    append_snapshot(path, my_jobs.SKILLS_COLUMNS, [row("2026-10-30", "hiredly", 5)], "2026-10-30", "hiredly")
    append_snapshot(path, my_jobs.SKILLS_COLUMNS, [row("2026-10-23", "hiredly", 6)], "2026-10-23", "hiredly")  # re-run
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys()) == my_jobs.SKILLS_COLUMNS
    got = sorted((r["snapshot_date"], r["site"], r["mentions"]) for r in rows)
    assert got == [("2026-10-23", "hiredly", "6"), ("2026-10-23", "jobstore", "4"), ("2026-10-30", "hiredly", "5")]


# ---------------------------------------------------------------- comparison with HN
def test_compare_with_hn_pools_sites_and_the_last_three_hn_months(tmp_path):
    skills = tmp_path / "skills.csv"
    skills.write_text(
        "snapshot_date,site,skill,mentions,n_listings,share\n"
        "2026-10-23,hiredly,Python,3,10,0.3\n"
        "2026-10-23,jobstore,Python,1,10,0.1\n"
        "2026-10-23,jobstore,Rust,1,10,0.1\n"
        "2026-09-01,hiredly,Go,9,10,0.9\n",
        encoding="utf-8",
    )
    hn = tmp_path / "hn.csv"
    hn.write_text(
        "month,skill,mentions,n_posts,share,share_smooth,thread_id,thread_url\n"
        "2026-07,Python,100,1000,0.1,0.1,1,u\n"
        "2026-08,Python,200,1000,0.2,0.2,2,u\n"
        "2026-09,Python,300,1000,0.3,0.3,3,u\n"
        "2026-10,Python,400,1000,0.4,0.4,4,u\n",
        encoding="utf-8",
    )
    rows = compare_with_hn(skills, hn, top=5)
    python = rows[0]
    assert python["skill"] == "Python" and python["my_mentions"] == 4 and python["my_n"] == 20
    assert python["my_share"] == pytest.approx(0.2)
    assert python["hn_share"] == pytest.approx((200 + 300 + 400) / 3000)  # last 3 months only
    assert rows[1]["skill"] == "Rust" and rows[1]["hn_share"] is None  # not in the HN file
    assert all(r["skill"] != "Go" for r in rows)  # older snapshot is ignored


def test_compare_with_hn_on_empty_file_returns_nothing(tmp_path):
    skills = tmp_path / "skills.csv"
    skills.write_text(",".join(my_jobs.SKILLS_COLUMNS) + "\n", encoding="utf-8")
    assert compare_with_hn(skills, tmp_path / "unused.csv") == []


# ---------------------------------------------------------------- command line gate
def test_cli_refuses_sites_with_unclear_terms_without_the_permission_flag(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the network must not be touched")

    monkeypatch.setattr(my_jobs, "run", boom)
    with pytest.raises(SystemExit):
        my_jobs.main(["--sites", "jobstore"])
    with pytest.raises(SystemExit):
        my_jobs.main(["--sites", "hiredly"])
    with pytest.raises(SystemExit):
        my_jobs.main(["--sites", "nosuchsite", "--permission-confirmed"])


def test_default_files_and_columns_match_the_documented_format():
    assert my_jobs.SKILLS_COLUMNS == ["snapshot_date", "site", "skill", "mentions", "n_listings", "share"]
    assert my_jobs.ROLES_COLUMNS == ["snapshot_date", "site", "role_id", "n", "share"]
    assert my_jobs.QUERIES == (
        "software engineer", "developer", "data engineer", "data scientist",
        "devops", "machine learning", "AI engineer", "mobile developer",
    )
    assert my_jobs.MAX_PAGES == 3 and my_jobs.MIN_INTERVAL_S == 3.0 and my_jobs.TIMEOUT_S == 30


# ---------------------------------------------------------------- review fixes
def test_run_refuses_a_site_whose_terms_need_written_permission(tmp_path, monkeypatch):
    fetched = []

    class NoNetwork:
        headers = {}

        def get(self, *a, **k):  # pragma: no cover - must never be reached
            fetched.append(a)
            raise AssertionError("fetched without permission")

    fetcher = PoliteFetcher(session=NoNetwork(), raw_dir=tmp_path / "raw")
    assert JobStore.terms_status != "no_clause_found" and Hiredly.terms_status != "no_clause_found"
    for sites in (["jobstore"], ["hiredly"], ["hiredly", "jobstore"]):
        with pytest.raises(PermissionError, match="written permission"):
            my_jobs.run(sites, fetcher=fetcher, write=False)
    assert fetched == []
    # with the flag the permission check passes and the run goes on (no site answers: a stopped site, no crash)
    ft = FakeTime()
    ok_fetcher, _, _ = make_fetcher({}, tmp_path, ft)
    monkeypatch.setattr(my_jobs, "SKILLS_CSV", tmp_path / "s.csv")
    monkeypatch.setattr(my_jobs, "ROLES_CSV", tmp_path / "r.csv")
    results = my_jobs.run(["jobstore"], fetcher=ok_fetcher, write=False, permission_confirmed=True, max_pages=1)
    assert [r.site for r in results] == ["jobstore"]


def test_main_passes_the_permission_flag_to_run(monkeypatch):
    seen = {}

    def fake_run(sites, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(my_jobs, "run", fake_run)
    assert my_jobs.main(["--sites", "jobstore", "--permission-confirmed", "--dry-run"]) == 0
    assert seen["permission_confirmed"] is True


def test_a_challenge_on_robots_txt_blocks_the_host_even_with_status_200(tmp_path):
    just_a_moment = FakeResponse(200, "<html><head><title>Just a moment...</title></head></html>")
    fetcher, session, _ = make_fetcher({"https://a.example/robots.txt": just_a_moment}, tmp_path)
    with pytest.raises(ChallengeDetected):
        fetcher.get("https://a.example/jobs")
    assert "a.example" in fetcher.blocked_hosts
    assert [c[0] for c in session.calls] == ["https://a.example/robots.txt"]       # the job page was never asked for
    marker = FakeResponse(200, "User-agent: *\nAllow: /\n", headers={"cf-mitigated": "challenge"})
    fetcher2, _, _ = make_fetcher({"https://b.example/robots.txt": marker}, tmp_path)
    with pytest.raises(ChallengeDetected):
        fetcher2.get("https://b.example/jobs")


def test_a_redirect_target_is_checked_against_robots_before_it_is_fetched(tmp_path):
    routes = {
        "https://a.example/robots.txt": OPEN_ROBOTS,
        "https://a.example/jobs": FakeResponse(302, "", headers={"Location": "https://c.example/private/list"}),
        "https://c.example/robots.txt": FakeResponse(200, "User-agent: *\nDisallow: /private/\n"),
        "https://c.example/private/list": FakeResponse(200, "<html>secret</html>"),
    }
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    with pytest.raises(RobotsDisallowed):
        fetcher.get("https://a.example/jobs")
    assert "https://c.example/private/list" not in [c[0] for c in session.calls]
    assert "https://c.example/robots.txt" in [c[0] for c in session.calls]          # the new host's rules were read


def test_an_allowed_redirect_is_followed_with_a_relative_location_and_the_final_url_is_kept(tmp_path):
    routes = {
        "https://a.example/robots.txt": OPEN_ROBOTS,
        "https://a.example/jobs": FakeResponse(301, "", headers={"location": "/jobs/all"}),
        "https://a.example/jobs/all": FakeResponse(200, "<html><title>Jobs</title>ok</html>"),
    }
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    page = fetcher.get("https://a.example/jobs")
    assert page.status == 200 and page.url == "https://a.example/jobs/all"


def test_redirects_stop_after_three_hops_and_automatic_redirects_are_off(tmp_path):
    routes = {"https://a.example/robots.txt": OPEN_ROBOTS}
    for i in range(6):
        routes[f"https://a.example/r{i}"] = FakeResponse(302, "", headers={"Location": f"/r{i + 1}"})
    seen_flags = []
    fetcher, session, _ = make_fetcher(routes, tmp_path)
    original = session.get

    def spy(url, timeout=None, allow_redirects=True):
        seen_flags.append(allow_redirects)
        return original(url, timeout=timeout, allow_redirects=allow_redirects)

    session.get = spy
    with pytest.raises(FetchFailed, match="redirects"):
        fetcher.get("https://a.example/r0")
    assert seen_flags and not any(seen_flags)
    hops = [c[0] for c in session.calls if re.search(r"/r[0-9]$", c[0])]
    assert hops == [f"https://a.example/r{i}" for i in range(4)]                    # the first request plus 3 hops
