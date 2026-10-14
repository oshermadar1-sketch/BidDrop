# app/services/slot_planner.py
# Minimal slot planner abstraction; adjust BLOCK_TIME_SEC to your chain.
# Comments in English.

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class SlotPlan:
    target_slot: int
    eta_seconds: int

BLOCK_TIME_SEC = 6  # adjust to your chain

def compute_next_slot(now_ts: Optional[int] = None, offset_blocks: int = 2) -> SlotPlan:
    """Return a simple plan for the next close slot (now + offset_blocks)."""
    now_ts = now_ts or int(time.time())
    eta_seconds = offset_blocks * BLOCK_TIME_SEC
    target_slot = (now_ts + eta_seconds) // BLOCK_TIME_SEC
    return SlotPlan(target_slot=target_slot, eta_seconds=eta_seconds)
