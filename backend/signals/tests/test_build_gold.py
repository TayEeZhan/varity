import pytest

from eval.build_gold import TOP_ALWAYS, build_gold, cohen_kappa, main, read_csv, sample_for_labelling, write_csv


def ranking(n=60):
    return [{"rank": str(i), "title": f"Story {i}", "url": f"https://e.x/{i}", "sources": "S", "final_score": "50",
             "p_must_know": "0.5"} for i in range(1, n + 1)]


def test_sheet_keeps_the_top_stories_hides_scores_and_is_reproducible():
    rows = sample_for_labelling(ranking(), size=50)
    assert len(rows) == 50 and set(rows[0]) == {"item", "title", "url", "sources", "label_A", "label_B", "final", "note"}
    urls = {r["url"] for r in rows}
    assert all(f"https://e.x/{i}" in urls for i in range(1, TOP_ALWAYS + 1))
    assert [r["url"] for r in rows] != [f"https://e.x/{i}" for i in range(1, 51)]  # shuffled, not in rank order
    assert rows == sample_for_labelling(ranking(), size=50)


def test_gold_uses_agreement_or_the_final_decision():
    sheet = [
        {"item": "1", "url": "u1", "label_A": "must_know", "label_B": "must_know", "final": "", "note": ""},
        {"item": "2", "url": "u2", "label_A": "minor", "label_B": "worth_a_look", "final": "minor", "note": "patch"},
        {"item": "3", "url": "u3", "label_A": "minor", "label_B": "worth_a_look", "final": "", "note": ""},
        {"item": "4", "url": "u4", "label_A": "", "label_B": "", "final": "", "note": ""},
    ]
    gold, report = build_gold(sheet)
    assert [(g["url"], g["gold_tier"], g["labeller"]) for g in gold] == [
        ("u1", "must_know", "A+B agreed"), ("u2", "minor", "A+B discussed")]
    assert report["needs_decision"] == ["3"] and report["agreement"] == pytest.approx(1 / 3)


def test_labels_are_case_insensitive_but_must_be_a_known_tier():
    gold, _ = build_gold([{"item": "1", "url": "u", "label_A": " Must_Know ", "label_B": "must_know", "final": ""}])
    assert gold[0]["gold_tier"] == "must_know"
    with pytest.raises(ValueError, match="1"):
        build_gold([{"item": "1", "url": "u", "label_A": "important", "label_B": "", "final": ""}])


def test_kappa():
    assert cohen_kappa([("must_know", "must_know"), ("minor", "minor")]) == 1.0
    assert cohen_kappa([("must_know", "minor"), ("minor", "must_know")]) < 0


def test_cli_round_trip(tmp_path):
    ranking_csv, sheet_csv, gold_csv = tmp_path / "r.csv", tmp_path / "s.csv", tmp_path / "g.csv"
    write_csv(ranking_csv, ("rank", "title", "url", "sources"), ranking(45))
    assert main(["sheet", "--ranking", str(ranking_csv), "--out", str(sheet_csv), "--size", "45"]) == 0
    rows = read_csv(sheet_csv)
    for row in rows:
        row["label_A"] = row["label_B"] = "worth_a_look"
    write_csv(sheet_csv, tuple(rows[0]), rows)
    assert main(["gold", "--sheet", str(sheet_csv), "--out", str(gold_csv)]) == 0
    assert len(read_csv(gold_csv)) == 45
