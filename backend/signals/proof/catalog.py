"""Project and cert catalogs, ranked by formula. No LLM here: every number comes from the role weights and the data.

Project rank = how much the match score would rise if the project passes:
    gain = sum over the project's skills of role_weight(s) * (1 - credit(s)) / total role weight
    credit: 0 for a gap, LEARNED_CREDIT for a skill backed only by ticked tasks, 1 for a held or proved skill.
Cert rank = share of the role's HN posts that name the cert * the user's coverage of its syllabus.
    With no HN count yet (data/cert_demand.json missing), certs rank by coverage only and say so.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load(name: str, data_dir: Path = DATA_DIR, required: bool = True) -> Any:
    path = data_dir / name
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"{name} is missing from data/")
        return None
    return _read(str(path), path.stat().st_mtime)


def projects(data_dir: Path = DATA_DIR) -> list[dict]:
    return load("projects.json", data_dir)["projects"]


def certs(data_dir: Path = DATA_DIR) -> list[dict]:
    return load("certs.json", data_dir)["certs"]


def project_by_id(project_id: str, data_dir: Path = DATA_DIR) -> dict | None:
    return next((p for p in projects(data_dir) if p["id"] == project_id), None)


def cert_by_id(cert_id: str, data_dir: Path = DATA_DIR) -> dict | None:
    return next((c for c in certs(data_dir) if c["id"] == cert_id), None)


def role_weights(role: Mapping) -> tuple[dict[str, float], dict[str, float]]:
    """(skill -> weight, skill -> credit) from one match_roles result."""
    weights = {s["skill"]: s["weight"] for s in role["have"] + role["gap"]}
    credit = {s["skill"]: s.get("credit", 1.0) for s in role["have"]}
    return weights, credit


def rank_projects(role: Mapping, items: list[dict]) -> list[dict]:
    """Projects for this role, best gain first. Gain is in match-score units (0..1)."""
    weights, credit = role_weights(role)
    total = sum(weights.values())
    out = []
    for p in items:
        if role["role_id"] not in p["roles"]:
            continue
        gain = sum(weights.get(s, 0.0) * (1.0 - credit.get(s, 0.0)) for s in p["skills"]) / total if total > 0 else 0.0
        closes = [s for s in p["skills"] if weights.get(s) and credit.get(s, 0.0) < 1.0]
        out.append({**p, "gain": gain, "closes": closes,
                    "why": why_line(closes, [s for s in p["skills"] if credit.get(s, 0.0) >= 1.0], role["name"])})
    out.sort(key=lambda p: (-p["gain"], p["level"] != "medium", p["title"]))
    return out


def why_line(closes: list[str], held: list[str], role_name: str) -> str:
    """Built from the formula's facts only. The fallback when proof/why.py has no checked model sentence."""
    if closes:
        text = f"Proves {', '.join(closes)}, which {role_name} posts ask for and you have not proved yet."
    else:
        text = f"Practice for {role_name}; it proves no new skill for your match score."
    if held:
        text += f" Uses {', '.join(held)}, which you already have."
    return text


def rank_certs(role: Mapping, items: list[dict], demand: Mapping | None) -> list[dict]:
    weights, credit = role_weights(role)
    by_cert = (demand or {}).get("certs", {})
    out = []
    for c in items:
        if role["role_id"] not in c["roles"]:
            continue
        syllabus = c["syllabus"]
        coverage = sum(credit.get(s, 0.0) for s in syllabus) / len(syllabus) if syllabus else 0.0
        row = (by_cert.get(c["id"]) or {}).get("roles", {}).get(role["role_id"])
        share = row["mentions"] / row["posts"] if row and row.get("posts") else None
        rank = share * coverage if share is not None else None
        out.append({**c, "coverage": coverage, "share": share, "mentions": row.get("mentions") if row else None,
                    "posts": row.get("posts") if row else None, "rankValue": rank,
                    "adds": [s for s in syllabus if s not in weights or credit.get(s, 0.0) == 0.0]})
    out.sort(key=lambda c: (c["rankValue"] is None, -(c["rankValue"] or 0.0), -c["coverage"], c["name"]))
    return out
