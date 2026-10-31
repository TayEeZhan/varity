"""Phase 2 impact check: run every synthetic profile through the real API and count the Phase 1 KPIs.

The Phase 1 KPIs were shares of test users. We ran no real-user test (rules: no real CVs), so this counts
what the built system gives each synthetic profile: the 3 example profiles and the 7 demo CVs (read by the
keyword pass, no LLM). Code only; no model is called. Writes data/impact_check.json.

    .venv\\Scripts\\python scripts/measure_impact.py
"""
from __future__ import annotations

import base64
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(TRENDSIGNAL_DOTENV="0", TRENDSIGNAL_LLM="off", ANTHROPIC_API_KEY="", KD_API_KEY="",
                  TRENDSIGNAL_DB=str(Path(tempfile.mkdtemp()) / "impact.db"))
sys.path.insert(0, str(ROOT / "backend" / "signals"))

from fastapi.testclient import TestClient  # noqa: E402

from trendsignal.config import load_settings  # noqa: E402
from trendsignal.jobs import load_context  # noqa: E402
from trendsignal.web.app import create_app  # noqa: E402

FREE = {"free", "free trial"}
STANCE = {r["skill"]: r["stance"] for r in csv.DictReader((ROOT / "data" / "exposure.csv").open(encoding="utf-8"))}


def profiles(client: TestClient):
    """(name, request headers) for each synthetic profile, saved through the same calls the app makes."""
    # Each profile gets its own test address (203.0.113.x, documentation range), so the per-address rate limits
    # meant for one visitor do not stop the run.
    addr = (f"203.0.113.{i}" for i in range(1, 255))
    for ex in client.get("/api/profile/examples").json()["data"]["examples"]:
        ip = {"X-Forwarded-For": next(addr)}
        yield ex["name"], {**ip, "X-Profile-Token": client.post("/api/profile/example", json={"id": ex["id"]}, headers=ip).json()["data"]["token"]}
    for f in sorted((ROOT / "demo-cvs").iterdir()):
        if f.name == "README.md":
            continue
        ip = {"X-Forwarded-For": next(addr)}
        body = {"file_name": f.name, "file_b64": base64.b64encode(f.read_bytes()).decode(), "use_ai": False}
        review = client.post("/api/cv/extract", json=body, headers=ip).json()["data"]
        kept = [r["skill_id"] for r in review["rows"] if r["default_keep"]]
        token = client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": kept}, headers=ip).json()["data"]["token"]
        yield f.name, {**ip, "X-Profile-Token": token}


def check(client: TestClient, name: str, h: dict) -> dict:
    sugg = {s: client.get("/api/roles/suggestions", params={"scenario": s}, headers=h).json()["data"] for s in ("moderate", "fast")}
    top = sugg["moderate"]["roles"][0] if sugg["moderate"]["roles"] else None
    out = {"profile": name, "ranked_roles": len(sugg["moderate"]["roles"])}
    if not top:
        return out
    answers = {s: client.get("/api/pathway", params={"roleId": top["roleId"], "scenario": s}, headers=h).json() for s in ("moderate", "fast")}
    if not all(a["success"] for a in answers.values()):
        return {**out, "top_role": top["name"], "pathway_error": next(a["error"] for a in answers.values() if not a["success"])}
    plans = {s: a["data"] for s, a in answers.items()}
    steps = plans["moderate"]["steps"]
    free_min = sum(s["minutes"] for s in steps if (s.get("resource") or {}).get("cost") in FREE)
    all_min = sum(s["minutes"] for s in steps) or 1
    return {**out,
            "top_role": top["name"], "match_pct": top["matchPct"],
            "explained": bool(top["gap"] is not None and top["breakdown"].get("raise") is not None),
            "steps": len(steps), "hours": plans["moderate"]["totals"]["hours"],
            "step_with_checked_free_resource": any((s.get("resource") or {}).get("cost") in FREE and s["resource"].get("url") for s in steps),
            "free_minutes_share": round(free_min / all_min, 3),
            "rising_or_ai_complement_step": any(s.get("trendLabel") == "Rising" or STANCE.get(s["skill"]) == "AI-complement" for s in steps),
            "steps_with_sdg_tag": sum(1 for s in steps if s.get("sdgTags")),
            "fast_shift_top3": [round(r.get("fastShift") or 0, 4) for r in sugg["fast"]["roles"][:3]],
            "scenario_changes_plan": [s["skill"] for s in steps] != [s["skill"] for s in plans["fast"]["steps"]]}


def main() -> int:
    client = TestClient(create_app(load_context(load_settings())))
    rows = [check(client, n, t) for n, t in profiles(client)]
    planned = [r for r in rows if r.get("steps")]
    share = lambda key: round(sum(1 for r in planned if r[key]) / len(rows), 3)  # noqa: E731 - out of all profiles
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profiles": len(rows),
        "kpi_4_4_plan_step_with_free_linked_resource": share("step_with_checked_free_resource"),
        "kpi_8_5_ranked_role_with_score_and_gap": round(sum(1 for r in rows if r.get("explained")) / len(rows), 3),
        "kpi_8_2_plan_has_rising_or_ai_complement_skill": share("rising_or_ai_complement_step"),
        "mean_free_minutes_share": round(sum(r["free_minutes_share"] for r in planned) / max(len(planned), 1), 3),
        "steps_tagged_sdg": f"{sum(r['steps_with_sdg_tag'] for r in planned)}/{sum(r['steps'] for r in planned)}",
        "fast_scenario_changes_plan": share("scenario_changes_plan"),
        "rows": rows,
    }
    (ROOT / "data" / "impact_check.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        print(r)
    print({k: v for k, v in summary.items() if k != "rows"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
