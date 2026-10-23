"""Tests for the skill ledger (profile.json v2) and its write rules."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake import ledger  # noqa: E402
from intake.ledger import LedgerError  # noqa: E402
from intake.models import MAX_SKILLS, Evidence, Interest  # noqa: E402

NOW = "2026-10-23T09:30:00Z"
AS_OF = "2026-10-23"


def cv(quote, years=None):
    return Evidence(source="cv", method="llm", context="work", quote=quote, years=years, added_at=NOW, added_by="intake")


def form(years):
    return Evidence(source="form", method="user_entry", context="user", years=years, added_at=NOW, added_by="user")


def implied(rule, from_skill):
    return Evidence(source="inferred", method="graph:requires", context="inferred", rule=rule,
                    from_skill=from_skill, added_at=NOW, added_by="intake")


def add(profile, skill_id, evidence, caller="intake", name=None):
    return ledger.add_evidence(profile, skill_id, name or skill_id.title(), evidence,
                               caller=caller, now=NOW, as_of=AS_OF)


@pytest.fixture
def empty():
    return ledger.new_profile("aina-synthetic", "Aina (synthetic)", now=NOW)


def test_new_cv_skill_is_stated_with_its_quote_and_years(empty):
    profile = add(empty, "python", cv("Built APIs in Python", years=2.8))
    entry = profile.skills[0]
    assert (entry.basis, entry.evidence_quote, entry.years, entry.years_as_of) == ("stated", "Built APIs in Python", 2.8, AS_OF)
    assert entry.evidence[0].id.startswith("sha1:")


def test_profile_is_never_changed_in_place(empty):
    add(empty, "python", cv("Built APIs in Python"))
    assert empty.skills == ()


def test_only_the_intake_may_write_cv_evidence(empty):
    with pytest.raises(LedgerError, match="Only the CV intake"):
        add(empty, "python", cv("Built APIs in Python"), caller="pathway")


def test_cv_evidence_needs_a_quote(empty):
    with pytest.raises(LedgerError, match="needs a quote"):
        add(empty, "python", Evidence(source="cv", method="llm", added_at=NOW, added_by="intake"))


def test_bad_skill_id_is_refused(empty):
    with pytest.raises(LedgerError):
        add(empty, "Not An Id!", form(1))


def test_same_evidence_twice_changes_nothing(empty):
    once = add(empty, "python", cv("Built APIs in Python"))
    assert add(once, "python", cv("built  APIs in python")) is once


def test_basis_is_the_strongest_evidence(empty):
    profile = add(empty, "javascript", implied("React requires JavaScript", "react"))
    assert profile.skills[0].basis == "implied"
    profile = add(profile, "javascript", form(1), caller="user")
    assert profile.skills[0].basis == "self_reported"
    profile = add(profile, "javascript", cv("Wrote JavaScript"))
    assert profile.skills[0].basis == "stated"


def test_cv_years_win_over_typed_years(empty):
    profile = add(empty, "python", form(9), caller="user")
    assert profile.skills[0].years == 9
    profile = add(profile, "python", cv("Built APIs in Python", years=2.8))
    assert profile.skills[0].years == 2.8


def test_removed_skill_stays_removed_until_the_user_restores_it(empty):
    profile = ledger.remove_skill(add(empty, "java", cv("Took a Java course")), "java", now=NOW)
    assert profile.skills == ()
    again = add(profile, "java", cv("Wrote Java services"))
    assert again.skills == ()
    assert len(again.removed[0].held_evidence) == 2
    restored = ledger.restore_skill(again, "java", now=NOW, as_of=AS_OF)
    assert [s.skill_id for s in restored.skills] == ["java"]
    assert len(restored.skills[0].evidence) == 2
    assert restored.removed == ()


def test_remove_and_restore_unknown_skill_fail(empty):
    with pytest.raises(LedgerError):
        ledger.remove_skill(empty, "python")
    with pytest.raises(LedgerError):
        ledger.restore_skill(empty, "python")


def test_interest_disappears_once_it_is_a_skill(empty):
    profile = ledger.add_interest(empty, Interest(phrase="Rust", skill_id="rust", quote="Learning Rust"), now=NOW)
    assert [i.skill_id for i in profile.interests] == ["rust"]
    profile = add(profile, "rust", cv("Wrote a Rust CLI"))
    assert profile.interests == ()
    assert ledger.add_interest(profile, Interest(phrase="Rust", skill_id="rust")) is profile


def test_skill_cap(empty):
    profile = empty
    for number in range(MAX_SKILLS):
        profile = add(profile, f"skill-{number}", form(1), caller="user")
    with pytest.raises(LedgerError, match="at most"):
        add(profile, "one-more", form(1), caller="user")


def test_round_trip_and_import_relabels_everything_as_unverified(empty):
    profile = add(add(empty, "python", cv("Built APIs in Python", years=2.8)), "javascript",
                  implied("React requires JavaScript", "react"))
    imported = ledger.import_profile(ledger.to_json(profile).encode("utf-8"), now=NOW, as_of=AS_OF)
    assert {e.source for s in imported.skills for e in s.evidence} == {"imported"}
    assert {s.basis for s in imported.skills} == {"self_reported"}
    assert imported.skills[0].evidence_quote is None  # an imported quote is not a checked CV quote


@pytest.mark.parametrize("data, message", [
    (b"x" * (ledger.MAX_IMPORT_BYTES + 1), "too large"),
    (b"\xff\xfe", "not valid JSON"),
    (b'{"schema_version": 2, "x": NaN}', "not valid JSON"),
    (b"[" * 100_000 + b"]" * 100_000, "not valid JSON|too large"),
    (b'{"schema_version": 1, "skills": []}', "not a Verity profile"),
    (json.dumps({"schema_version": 2, "profile_id": "a", "name": "A", "updated_at": NOW,
                 "skills": [], "hacker": True}).encode(), "not a Verity profile"),
], ids=["too-large", "not-utf8", "nan", "deep-nesting", "old-schema", "extra-field"])
def test_import_refuses_bad_files(data, message):
    with pytest.raises(LedgerError, match=message):
        ledger.import_profile(data)


def test_demo_profile_file_is_valid():
    path = Path(__file__).resolve().parent.parent / "intake" / "samples" / "aina-synthetic.json"
    profile = ledger.load_trusted_profile(path)
    assert profile.schema_version == 2
    assert all(entry.evidence for entry in profile.skills)
    assert {entry.basis for entry in profile.skills} <= {"stated", "implied", "self_reported", "suggested"}
