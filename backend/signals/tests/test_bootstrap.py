"""A fresh deploy (empty database) runs one pipeline pass in the background; a populated one does not."""
from trendsignal import jobs


def test_bootstrap_runs_once_only_when_no_ranked_run_exists(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, "run_pipeline_if_idle", lambda c: calls.append(c))
    jobs.bootstrap_if_empty(ctx).join(5)
    assert calls == [ctx]
    monkeypatch.setattr(jobs, "latest_run_id", lambda s: "run-1")
    assert jobs.bootstrap_if_empty(ctx) is None and len(calls) == 1


def test_bootstrap_failure_is_logged_not_raised(ctx, monkeypatch):
    def boom(c):
        raise RuntimeError("network down")

    monkeypatch.setattr(jobs, "run_pipeline_if_idle", boom)
    jobs.bootstrap_if_empty(ctx).join(5)
