"""Varity's Evidence area: the skills radar and the Method page (backtests, AI-exposure cross-check, sources).

Every number is read from the files in data/ at request time (cached by file mtime). Nothing is typed here.
A missing required file is a clear 500 with a code, never a crash. Optional files hide only their own section.
"""

from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request

from advisor import service
from advisor.mapping import map_profile, taxonomy_index
from trendsignal.config import Settings
from trendsignal.web.app import RateLimiter, envelope
from trendsignal.web.auth_api import owner_of
from trendsignal.web.cv_api import client_ip, load_profile

from engine import radar as radar_mod  # noqa: E402  (advisor.service puts the repo root on sys.path)

DATA_DIR = service.DATA_DIR
EVIDENCE_LIMIT_PER_MINUTE = 30
SCENARIOS = ("moderate", "fast")


class DataMissing(Exception):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


@lru_cache(maxsize=32)
def _read(path: str, mtime: float) -> Any:
    """`mtime` only keys the cache, so an engine refresh is picked up."""
    with open(path, encoding="utf-8", newline="") as fh:
        if path.endswith(".json"):
            return json.load(fh)
        if path.endswith(".csv"):
            return list(csv.DictReader(fh))
        return fh.read()


def load(name: str, data_dir: Path, required: bool = True) -> Any:
    path = data_dir / name
    try:
        return _read(str(path), path.stat().st_mtime)
    except (OSError, ValueError) as exc:  # missing, unreadable or not valid JSON
        if required:
            raise DataMissing(name) from exc
        return None


def contested_skills(data_dir: Path) -> set[str] | None:
    """Skills whose AI stance the other published indices do not support. None when the file is missing."""
    rows = load("exposure_robustness.csv", data_dir, required=False)
    if rows is None:
        return None
    return {r["skill"] for r in rows if (r.get("stance_robust") or "").strip().lower() == "false"}


def held_skills(settings: Settings, owner: str | None, data_dir: Path) -> tuple[list[str], list[str]]:
    """(taxonomy skills held by the saved profile, names that match no taxonomy skill). Both empty without a profile."""
    profile = load_profile(settings, owner)
    taxonomy = load("taxonomy.json", data_dir, required=False)
    if profile is None or not taxonomy:
        return [], []
    held, unmapped = map_profile(profile, taxonomy_index(taxonomy))
    return sorted(held), unmapped


def radar_payload(settings: Settings, owner: str | None, data_dir: Path = DATA_DIR) -> dict:
    as_of = service.replay_as_of()  # a replay shows the scores cut at that month
    scores = service._replayed(as_of)["scores"] if as_of else load("skill_scores.json", data_dir)
    backtest = load("backtest.json", data_dir, required=False)
    contested = contested_skills(data_dir)
    held, unmapped = held_skills(settings, owner, data_dir)
    skills = scores.get("skills") or []
    radar = radar_mod.radar_points(skills, held, contested or ())
    by_name = {s.get("skill"): s for s in skills}
    for point in radar["points"]:
        point["forecast"] = {k: (by_name[point["skill"]].get("forecast") or {}).get(k) for k in SCENARIOS}
    interval = scores.get("interval") or {}
    return {
        "points": radar["points"], "shareCut": radar["share_cut"], "skipped": radar["skipped"],
        "held": held, "unmapped": unmapped,
        "sentences": radar_mod.summary_sentences(radar, held), "howToRead": radar_mod.how_to_read(backtest),
        "asOf": scores.get("as_of"), "partialMonth": bool(scores.get("partial_month")),
        "generatedAt": scores.get("generated_at"), "dataWindow": scores.get("data_window"),
        "band": {"label": interval.get("label"), "level": interval.get("level"), "model": interval.get("model")},
        "contestedKnown": contested is not None,
        "source": {"file": "data/skill_scores.json", "robustness": "data/exposure_robustness.csv",
                   "text": "Hacker News 'Who is hiring?' posts; AI stance from the Anthropic Economic Index"},
    }


def backtest_view(bt: dict) -> dict:
    """The parts of a backtest file the Method page shows, as read."""
    models = [{"model": name, "inProduction": m.get("in_production"), "early": m.get("early_mae_pp"),
               "test": m.get("test_mae_pp"), "gainVsNaive": m.get("test_h12_vs_naive")}
              for name, m in (bt.get("models") or {}).items()]
    cov = bt.get("coverage") or {}
    interval = bt.get("interval")
    return {
        "kind": bt.get("kind") or "skill", "generatedAt": bt.get("generated_at"), "dataWindow": bt.get("data_window"),
        "origins": bt.get("origins"), "sampleNote": bt.get("sample_note"), "models": models,
        "chosenModel": bt.get("chosen_model"), "chosenBecause": bt.get("chosen_because"), "verdict": bt.get("verdict"),
        "interval": interval.get("type") if isinstance(interval, dict) else None,
        "coverage": {k: cov.get(k) for k in ("label", "nominal", "test_h12", "test_mean_band_width_h12_pp",
                                             "share_group_definition", "by_share_group")},
        "trendLabel": bt.get("trend_label_backtest"), "caveats": bt.get("caveats") or [],
    }


def source_links(sources_md: str) -> list[dict]:
    """Title and first URL of each numbered section of data/SOURCES.md."""
    found = []
    for block in re.split(r"(?m)^## ", sources_md)[1:]:
        title, _, body = block.partition("\n")
        url = re.search(r"https?://[^\s)>`,]+", body)
        if re.match(r"\d+\.", title) and url:
            found.append({"title": title.strip(), "url": url.group(0).rstrip(".")})
    return found


def exposure_view(data_dir: Path) -> dict | None:
    agreement = load("exposure_agreement.json", data_dir, required=False)
    occupations = load("exposure_occupations.csv", data_dir, required=False)
    if agreement is None and occupations is None:
        return None
    out: dict = {"occupations": [
        {"category": r["category"], "title": r["occupation_title"], "code": r["onet_soc"],
         "automationPct": float(r["automation_pct"])} for r in occupations or []]}
    if agreement is not None:
        from engine.exposure_indices import agreement_text, correlation_text, crosscheck_rows  # pandas: load on demand
        out.update({
            "crossCheck": crosscheck_rows(agreement), "correlation": correlation_text(agreement),
            "robustCategories": agreement.get("robust_categories") or [],
            "contestedCategories": agreement.get("contested_categories") or [],
            "productionStanceChanged": agreement.get("production_stance_changed"),
            "agreementText": agreement_text(agreement).replace("**", ""),
            "sources": agreement.get("sources"), "caveats": agreement.get("caveats") or []})
    return out


def k_view(data_dir: Path) -> dict | None:
    k = load("k_estimate.json", data_dir, required=False)
    if k is None:
        return None
    from engine.k_estimate import k_caption, k_line
    return {"assumedK": k.get("assumed_k_in_production"), "line": k_line(k), "caption": k_caption(k),
            "headline": k.get("headline"), "generatedAt": k.get("generated_at"), "label": "assumption"}


def evidence_payload(data_dir: Path = DATA_DIR) -> dict:
    skills_bt = load("backtest.json", data_dir)
    roles_bt = load("role_backtest.json", data_dir, required=False)
    scores = load("skill_scores.json", data_dir, required=False) or {}
    sources_md = load("SOURCES.md", data_dir, required=False)
    checked = re.search(r"Checked on ([^.\n]+)", sources_md or "")
    exposure = exposure_view(data_dir)
    k = k_view(data_dir)
    missing = [name for name, value in (("role_backtest.json", roles_bt), ("SOURCES.md", sources_md),
                                        ("exposure_agreement.json", (exposure or {}).get("crossCheck")),
                                        ("k_estimate.json", k)) if value is None]
    return {
        "asOf": scores.get("as_of"),
        "backtests": {"skills": backtest_view(skills_bt), "roles": backtest_view(roles_bt) if roles_bt else None},
        "exposure": exposure, "k": k,
        "sources": source_links(sources_md) if sources_md else [],
        "sourcesChecked": checked.group(1).strip() if checked else None,
        "missing": missing,
    }


def add_evidence_routes(app: FastAPI, settings: Settings, data_dir: Path = DATA_DIR) -> None:
    limiter = RateLimiter(EVIDENCE_LIMIT_PER_MINUTE)

    def guarded(request: Request, build):
        if not limiter.allow(client_ip(request)):
            return envelope(error="too many requests, try again in a minute", status=429, meta={"code": "RATE_LIMITED"})
        try:
            return envelope(build())
        except DataMissing as exc:
            return envelope(error=f"evidence data is missing: {exc.name} (run the engine, see data/SOURCES.md)",
                            status=500, meta={"code": "EVIDENCE_DATA_MISSING", "file": exc.name})

    @app.get("/api/skills/radar")
    def api_skills_radar(request: Request, x_profile_token: str | None = Header(default=None)):
        """Every skill by demand share and tested change; the saved profile's skills are marked."""
        return guarded(request, lambda: radar_payload(settings, owner_of(request, x_profile_token), data_dir))

    @app.get("/api/evidence")
    def api_evidence(request: Request):
        """Backtests, AI-exposure cross-check, the k assumption and the sources, read from data/."""
        return guarded(request, lambda: evidence_payload(data_dir))
