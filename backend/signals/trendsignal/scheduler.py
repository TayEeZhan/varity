"""Background schedule: the ranking pipeline every 15 minutes (each source still respects its own
cadence), writing data/ranked/latest.json and latest.csv after each run. The prose briefs (daily at
08:00, weekly on Monday 08:05) are outside the core ranker and run only with TRENDSIGNAL_BRIEFS=1."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from trendsignal.jobs import AppContext, make_digest, run_pipeline_if_idle

log = logging.getLogger(__name__)

PIPELINE_EVERY_MINUTES = 15
FIRST_RUN_DELAY_SECONDS = 30
REFRESH_HOUR = 6  # once a day; HN data changes slowly, and each run downloads the whole current thread


def _logged(name: str, job: Callable[[], object]) -> Callable[[], None]:
    def run() -> None:
        try:
            job()
        except Exception:  # a scheduled job must never kill the scheduler thread
            log.exception("scheduled job %s failed", name)
    return run


def refresh_forecast() -> None:
    """Daily: newest HN thread -> skill and role demand, scores and forecast -> new store snapshot.

    engine.scheduled switches latest.json only on success, so a failure keeps the last good data.
    """
    from advisor import service  # noqa: F401 - puts the verity root on sys.path for engine/
    from engine import scheduled

    summary = scheduled.run()
    (log.info if summary["ok"] else log.warning)("forecast refresh: %s", summary)


def build_scheduler(ctx: AppContext) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        timezone=ctx.settings.timezone,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 600},
    )
    scheduler.add_job(_logged("pipeline", lambda: run_pipeline_if_idle(ctx)), "interval", minutes=PIPELINE_EVERY_MINUTES,
                      id="pipeline", next_run_time=datetime.now(scheduler.timezone) + timedelta(seconds=FIRST_RUN_DELAY_SECONDS))
    scheduler.add_job(_logged("forecast_refresh", refresh_forecast), "cron", hour=REFRESH_HOUR, minute=30,
                      id="forecast_refresh")
    if ctx.settings.write_briefs:
        scheduler.add_job(_logged("daily_digest", lambda: make_digest(ctx, "daily")), "cron", hour=8, minute=0,
                          id="daily_digest")
        scheduler.add_job(_logged("weekly_digest", lambda: make_digest(ctx, "weekly")), "cron", day_of_week="mon",
                          hour=8, minute=5, id="weekly_digest")
    return scheduler
