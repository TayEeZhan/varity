"""KrackedDevs client and the provider switch in llm_labels. A fake opener stands in for the network."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import llm_client, llm_labels  # noqa: E402


class FakeResp:
    def __init__(self, content="hi", p=100, c=10, cost=None):
        self.headers = {llm_client.COST_HEADER: cost} if cost else {}
        self._body = json.dumps({"choices": [{"message": {"content": content}}],
                                 "usage": {"prompt_tokens": p, "completion_tokens": c}}).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(*results):
    seen = []

    def opener(req, timeout):
        seen.append(req)
        r = results[min(len(seen), len(results)) - 1]
        if isinstance(r, Exception):
            raise r
        return r
    opener.seen = seen
    return opener


def http_error(code, msg="nope"):
    return urllib.error.HTTPError("u", code, msg, {}, io.BytesIO(msg.encode()))


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("KD_API_KEY", "sk-test-secret")


def test_success_returns_text_and_logs_usage_without_the_key(tmp_path):
    log = tmp_path / "u.csv"
    op = opener_for(FakeResp("answer", 1_000_000, 1_000_000))
    out = llm_client.kd_call("deepseek-v4-flash", "label", log, 15, opener=op)("sys", "user")
    assert out == "answer"
    body = json.loads(op.seen[0].data)
    assert body["temperature"] == 0 and body["messages"][0] == {"role": "system", "content": "sys"}
    assert op.seen[0].full_url == "https://litellm.rapidscreen.io/v1/chat/completions"
    assert llm_client.job_usage(log, "label") == (1_000_000, 1_000_000, pytest.approx(0.42))
    assert "sk-test-secret" not in log.read_text() and "krackeddevs" in log.read_text()


def test_gateway_cost_header_beats_assumed_prices(tmp_path):
    log = tmp_path / "u.csv"
    llm_client.kd_call("gpt-5.4-mini", "x", log, 15, opener=opener_for(FakeResp(cost="0.5")))("s", "u")
    assert llm_client.job_usage(log, "x")[2] == 0.5 and "gateway" in log.read_text()


def test_budget_cap_stops_before_the_next_call(tmp_path):
    log = tmp_path / "u.csv"
    op = opener_for(FakeResp(cost="2"))
    call = llm_client.kd_call("m", "label", log, 1.5, opener=op)
    call("s", "u")
    with pytest.raises(llm_client.BudgetExceeded):
        call("s", "u")
    assert len(op.seen) == 1


def test_401_gives_a_clear_error_and_retries_stop(tmp_path):
    op = opener_for(http_error(401, "bad key"))
    with pytest.raises(llm_client.KDError, match="401.*KD_API_KEY"):
        llm_client.kd_call("m", "j", tmp_path / "u.csv", 15, opener=op)("s", "u")
    assert len(op.seen) == 1


def test_429_is_retried_then_succeeds(tmp_path):
    op = opener_for(http_error(429), http_error(503), FakeResp("ok"))
    out = llm_client.kd_call("m", "j", tmp_path / "u.csv", 15, opener=op, sleep=lambda s: None)("s", "u")
    assert out == "ok" and len(op.seen) == 3


def test_llm_labels_uses_kd_when_key_is_set_and_quote_check_still_drops(monkeypatch, tmp_path):
    monkeypatch.setenv("KD_LABEL_MODEL", "deepseek-v4-flash")
    assert llm_labels.has_credentials() and llm_labels.model_name() == "krackeddevs/deepseek-v4-flash"
    answer = json.dumps({"1": {"backend_engineer": "Backend Engineer", "data_engineer": "invented words"}})
    op = opener_for(FakeResp(answer))
    real = llm_client.kd_call
    monkeypatch.setattr(llm_client, "kd_call", lambda m, j: real(m, j, tmp_path / "u.csv", 15, opener=op))
    labels, dropped = llm_labels.classify([("1", "Acme | Backend Engineer | remote")],
                                          [{"id": "backend_engineer", "name": "B", "description": "d"},
                                           {"id": "data_engineer", "name": "D", "description": "d"}],
                                          llm_labels.label_call())
    assert labels == {"1": {"backend_engineer"}} and dropped == 1
    assert op.seen[0].get_header("Authorization") == "Bearer sk-test-secret"


def test_without_kd_key_the_claude_path_is_kept(monkeypatch):
    monkeypatch.delenv("KD_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert llm_labels.model_name() == "claude-haiku-5-5" and llm_labels.labeller_name() == "claude"


def test_backfill_limit_is_a_dry_run_that_writes_nothing(tmp_path):
    (tmp_path / "roles.json").write_text(json.dumps([{"id": "backend_engineer", "name": "B", "description": "d",
                                                      "title_pattern": "backend engineer", "sdg": [], "ranked": True}]))
    (tmp_path / "hn_threads.csv").write_text("thread_id,month,title,created_utc,n_comments\n9,2026-11,t,0,2\n")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "9.json").write_text(json.dumps({"children": [{"id": 1, "text": "Acme | Backend Engineer"},
                                                          {"id": 2, "text": "Beta | Chef"}]}))
    r = llm_labels.backfill(tmp_path, raw, False, call=lambda s, u: "{}", limit=1)
    assert r["dry_run"] and r["posts"] == 1 and not (tmp_path / "llm_role_labels.csv").exists()
    assert not (tmp_path / "role_labeller.json").exists()
