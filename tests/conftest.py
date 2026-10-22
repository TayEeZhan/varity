"""Shared test setup: keep every test away from the real snapshot store and live folders."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import live  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Point the store and the live-snapshot folder at empty temp folders, and forget the Replit setup.

    Without this, a test that clicks "Refresh live data" would save a snapshot into the
    real <tempdir>/verity_store, and later tests would show it as "newer data".
    """
    monkeypatch.setenv("VERITY_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("VERITY_LIVE_DIR", str(tmp_path / "live"))
    for name in ("REPL_ID", "REPLIT_DEPLOYMENT", "VERITY_STORE", "VERITY_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    live._cached_start_dir.clear()
    yield
    live._cached_start_dir.clear()


def write_data_folder(folder: Path, generated_at: str = "2026-10-22T01:00:00Z", marker: str = "a") -> Path:
    """A small, valid set of snapshot files. `marker` makes the content differ between folders."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skill_scores.json").write_text(
        json.dumps({"generated_at": generated_at, "as_of": "2026-10", "marker": marker}), encoding="utf-8")
    (folder / "demand_monthly.csv").write_text(f"month,skill,n\n2026-10,Python,{marker}\n", encoding="utf-8")
    (folder / "hn_threads.csv").write_text("thread_id,month\n1,2026-10\n", encoding="utf-8")
    (folder / "ai_context_monthly.csv").write_text("month,n\n2026-10,1\n", encoding="utf-8")
    return folder


@pytest.fixture
def data_folder(tmp_path) -> Path:
    return write_data_folder(tmp_path / "work")
