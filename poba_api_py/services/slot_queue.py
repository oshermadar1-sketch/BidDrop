# app/services/slot_queue.py
# APScheduler wrapper for scheduling jobs at UTC times (tz-aware).
# Comments in English.

from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from typing import Callable
from datetime import datetime, timezone

_scheduler: BackgroundScheduler | None = None

def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.start()
    return _scheduler

def enqueue_at(run_at_utc: datetime, fn: Callable, *args, **kwargs) -> str:
    """Schedule a one-off job at an absolute UTC time; returns job id.
    If run_at_utc is naive, assume UTC.
    """
    if run_at_utc.tzinfo is None:
        run_at_utc = run_at_utc.replace(tzinfo=timezone.utc)
    sched = get_scheduler()
    trig = DateTrigger(run_date=run_at_utc)
    job = sched.add_job(fn, trigger=trig, args=args, kwargs=kwargs, coalesce=True, misfire_grace_time=30)
    return job.id
