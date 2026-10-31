"""KrackedDevs LiteLLM gateway (OpenAI-compatible), stdlib only. Bulk and background AI jobs use it.

kd_call(model, job) returns call(system, user) -> text, like engine.llm_labels.claude_call.
Every call is logged to data/llm_usage.csv (tokens and USD only, never the key or any text).
A per-job budget guard stops a run before it spends past the cap. See tasks/plan-credits.md.
"""
from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

USAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "llm_usage.csv"
USAGE_COLUMNS = ["time", "job", "provider", "model", "prompt_tokens", "completion_tokens", "est_usd", "cost_source"]
DEFAULT_BASE_URL = "https://litellm.rapidscreen.io/v1"
COST_HEADER = "x-litellm-response-cost"
# shortcut: assumed list prices (USD per million tokens, input and output), not KrackedDevs' real prices;
# replace with the gateway's real spend. A model not listed gets UNKNOWN_PRICE, which is high on purpose.
PRICES = {"deepseek-v4-flash": (0.14, 0.28), "gpt-5.4-nano": (0.05, 0.40), "gpt-5.4-mini": (0.25, 2.00)}
UNKNOWN_PRICE = (2.50, 10.00)


class KDError(RuntimeError):
    """The gateway refused or failed (bad key, model not on the key, key budget, network)."""


class BudgetExceeded(KDError):
    """The logged spend for this job reached the cap."""


def kd_configured() -> bool:
    return bool(os.environ.get("KD_API_KEY"))


def label_model() -> str:
    return os.environ.get("KD_LABEL_MODEL", "deepseek-v4-flash")


def review_model() -> str:
    return os.environ.get("KD_REVIEW_MODEL", "gpt-5.4-mini")


def _cap() -> float:
    return float(os.environ.get("KD_CAP_USD", "15"))


def job_usage(usage_path: Path | str, job: str) -> tuple[int, int, float]:
    """(prompt tokens, completion tokens, USD) logged so far for one job."""
    p = Path(usage_path)
    if not p.is_file():
        return 0, 0, 0.0
    with p.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["job"] == job]
    return (sum(int(r["prompt_tokens"]) for r in rows), sum(int(r["completion_tokens"]) for r in rows),
            sum(float(r["est_usd"]) for r in rows))


def _log(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=USAGE_COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow(row)


def kd_call(model: str, job: str, usage_path: Path | str = USAGE_PATH, cap_usd: float | None = None,
            prices: dict = PRICES, opener: Callable | None = None, sleep: Callable = time.sleep) -> Callable[[str, str], str]:
    opener = opener or urllib.request.urlopen
    usage_path = Path(usage_path)

    def call(system: str, user: str) -> str:
        key = os.environ.get("KD_API_KEY")
        if not key:
            raise KDError("KD_API_KEY is not set")
        cap = _cap() if cap_usd is None else cap_usd
        spent = job_usage(usage_path, job)[2]
        if spent >= cap:
            raise BudgetExceeded(f"job '{job}' has spent about ${spent:.2f} of its ${cap:.2f} cap (data/llm_usage.csv)")
        body = json.dumps({"model": model, "temperature": 0,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(os.environ.get("KD_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/chat/completions",
                                     data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with opener(req, timeout=60) as resp:
                    cost_header = resp.headers.get(COST_HEADER)
                    doc = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300] if hasattr(exc, "read") else ""
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    sleep(2 ** attempt * 2)
                    continue
                hint = {401: "bad KD_API_KEY", 400: "model not on this key, or a bad request"}.get(exc.code, "gateway error")
                raise KDError(f"KrackedDevs HTTP {exc.code} ({hint}): {detail}") from exc
            except (urllib.error.URLError, OSError, ValueError) as exc:
                if attempt < 2:
                    sleep(2 ** attempt * 2)
                    continue
                raise KDError(f"KrackedDevs unreachable: {type(exc).__name__}: {exc}") from exc
        try:
            text = doc["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise KDError("KrackedDevs answer has no choices[0].message.content") from exc
        usage = doc.get("usage") or {}
        p_tok, c_tok = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        try:
            usd, source = float(cost_header), "gateway"
        except (TypeError, ValueError):
            p_in, p_out = prices.get(model, UNKNOWN_PRICE)
            usd, source = (p_tok * p_in + c_tok * p_out) / 1e6, "assumed_price"
        _log(usage_path, {"time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "job": job,
                          "provider": "krackeddevs", "model": model, "prompt_tokens": p_tok,
                          "completion_tokens": c_tok, "est_usd": f"{usd:.6f}", "cost_source": source})
        return text
    return call
