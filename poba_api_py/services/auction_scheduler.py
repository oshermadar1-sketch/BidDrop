# app/services/auction_scheduler.py
# Schedules an optional on-chain finalize call at a near-future UTC time.
# TZ-aware (no utcfromtimestamp). Comments in English.

from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone
import time

# If slot_planner is elsewhere, update the import path accordingly.
from core.slot_planner import compute_next_slot
from .slot_queue import enqueue_at

# from app.chain.client import submit_close_extrinsic  # when ready

def _close_auction_job(auction_id: str | int, winner_ss58: Optional[str]) -> None:
    """Executed by scheduler at target time; call your chain here."""
    try:
        # submit_close_extrinsic(auction_id=auction_id, winner=winner_ss58)
        print(f"[close_auction_job] auction={auction_id} winner={winner_ss58}")
    except Exception as e:
        print("[close_auction_job] FAILED:", e)

def schedule_auction_close(
    auction_id: str | int,
    winner_ss58: Optional[str] = None,
    now_ts: Optional[int] = None,
) -> str:
    """Plan a close call a few blocks in the future (Aura-like)."""
    plan = compute_next_slot(now_ts=now_ts, offset_blocks=2)
    base_ts = now_ts or int(time.time())
    run_at_utc = datetime.fromtimestamp(base_ts + plan.eta_seconds, tz=timezone.utc)  # tz-aware
    job_id = enqueue_at(run_at_utc, _close_auction_job, auction_id, winner_ss58)
    return job_id
