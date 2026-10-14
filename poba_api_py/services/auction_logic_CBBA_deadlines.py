# app/services/auction_logic_CBBA_deadlines.py
# Unifies parcels (PARCEL) and rides (RIDE) under a CBBA-like round with deadlines.
# All comments in English.

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Literal
import math
import time

JobType = Literal["PARCEL", "RIDE"]

@dataclass
class Courier:
    """Provider entity (driver/courier).
    kind can be "PARCEL", "RIDE", or "BOTH" to indicate what they accept.
    """
    id: int
    ss58: Optional[str] = None  # for on-chain finalize if you need it
    lat: float = 0.0
    lng: float = 0.0
    speed_kmh: float = 30.0
    capacity_kg: float = 0.0
    max_detour_km: float = 10.0
    reliability: float = 0.9  # 0..1
    kind: Literal["PARCEL", "RIDE", "BOTH"] = "BOTH"
    hard_deadline_grace_min: int = 10

@dataclass
class Job:
    """Unified job for both PARCEL (shipments) and RIDE (rides)."""
    id: int
    type: JobType
    pickup_lat: float
    pickup_lng: float
    drop_lat: float
    drop_lng: float
    earliest_ts: int  # unix seconds (or minutes, but be consistent!)
    latest_ts: int
    bid_price: float  # For RIDE: requester max willing to pay; for PARCEL: same
    weight_kg: float = 0.0  # Used for PARCEL capacity checks

@dataclass
class ParcelAsk:
    """Optional per (courier, job) ask price for PARCEL.
    If you do not store asks, you can synthesize them using heuristics.
    """
    courier_id: int
    job_id: int
    ask_price: float

# ---------------------- Utility helpers ----------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance between two coordinates in KM."""
    R = 6371.0
    p = math.pi / 180.0
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = 0.5 - math.cos(dlat)/2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos(dlon)) / 2
    return 2 * R * math.asin(math.sqrt(a))

# ---------------------- Feasibility & scoring ----------------------

def feasible(c: Courier, j: Job, now_ts: int) -> Tuple[bool, Dict[str, float]]:
    """Check basic feasibility constraints and return (ok, metrics)."""
    if c.kind != "BOTH" and c.kind != j.type:
        return False, {"reason": 1}
    if j.type == "PARCEL" and j.weight_kg > (c.capacity_kg or 0.0):
        return False, {"reason": 2}

    # Rough detour estimate: distance origin->pickup + pickup->drop
    d1 = haversine_km(c.lat, c.lng, j.pickup_lat, j.pickup_lng)
    d2 = haversine_km(j.pickup_lat, j.pickup_lng, j.drop_lat, j.drop_lng)
    detour = d1 + d2
    if detour > c.max_detour_km:
        return False, {"reason": 3, "detour": detour}

    # Time window rough check
    km_per_min = max(0.001, (c.speed_kmh or 30.0) / 60.0)
    eta_to_pickup_min = d1 / km_per_min
    # Earliest pickup should be reachable before latest, with some grace
    if now_ts + int(eta_to_pickup_min * 60) > (j.latest_ts + c.hard_deadline_grace_min * 60):
        return False, {"reason": 4, "eta_pickup_min": eta_to_pickup_min}

    return True, {"detour_km": detour, "eta_pickup_min": eta_to_pickup_min}


def score_bid(c: Courier, j: Job, metrics: Dict[str, float], ask_lookup: Dict[Tuple[int,int], float]) -> float:
    """Higher is better score combining price, detour, ETA, and reliability.
    If ask price exists (for PARCEL), prefer profitable matches under bidder/requester constraints.
    """
    detour_km = metrics.get("detour_km", 999.0)
    eta_min = metrics.get("eta_pickup_min", 999.0)

    # Ask price fallback heuristic if not explicitly provided
    ask = ask_lookup.get((c.id, j.id))
    if ask is None:
        # Simple heuristic: base cost ~ 1.8₪/km * detour + small ETA component
        ask = 1.8 * detour_km + 0.05 * eta_min

    # Requester's max willingness to pay
    max_pay = j.bid_price or 0.0

    # Infeasible economically if ask > max price (sealed double-auction rule)
    if ask > max_pay:
        return -1e9

    # Normalize terms (inverse for detour and ETA)
    eps = 1e-6
    price_term  = 1.0 / (ask + eps)
    detour_term = 1.0 / (detour_km + 0.1)
    eta_term    = 1.0 / (eta_min + 1.0)
    rel_term    = c.reliability

    # Weights can be tuned per product
    w_price, w_detour, w_eta, w_rel = 0.55, 0.2, 0.15, 0.1
    return (w_price*price_term + w_detour*detour_term + w_eta*eta_term + w_rel*rel_term)

# ---------------------- CBBA-like round ----------------------

def run_cbba_round(
    couriers: List[Courier],
    jobs: List[Job],
    parcel_asks: List[ParcelAsk],
    now_ts: Optional[int] = None,
    max_rounds: int = 3,
) -> Dict[int, List[int]]:
    """Run a simplified CBBA-like auction round.
    Returns assignment as {courier_id: [job_id, ...]}.
    This is intentionally simple and compatible with your older code.
    """
    now_ts = now_ts or int(time.time())

    # Pre-compute ask lookup for fast access
    ask_lookup: Dict[Tuple[int,int], float] = {}
    for a in parcel_asks:
        ask_lookup[(a.courier_id, a.job_id)] = a.ask_price

    # Each courier picks best available job it can feasibly do (greedy CBBA round)
    remaining_job_ids = {j.id for j in jobs}
    job_map = {j.id: j for j in jobs}

    assignment: Dict[int, List[int]] = {c.id: [] for c in couriers}

    for _ in range(max_rounds):
        any_claim = False
        # Compute all (courier, job) scores
        scored_choices: List[Tuple[float, int, int]] = []  # (score, courier_id, job_id)
        for c in couriers:
            for j_id in list(remaining_job_ids):
                j = job_map[j_id]
                ok, metrics = feasible(c, j, now_ts)
                if not ok:
                    continue
                s = score_bid(c, j, metrics, ask_lookup)
                if s <= -1e8:
                    continue
                scored_choices.append((s, c.id, j.id))

        if not scored_choices:
            break

        # Sort by score desc and let them claim greedily (conflicts resolved by score)
        scored_choices.sort(reverse=True, key=lambda t: t[0])
        claimed_jobs: set[int] = set()
        claimed_by_courier: set[int] = set()

        for score, c_id, j_id in scored_choices:
            if j_id in claimed_jobs or j_id not in remaining_job_ids:
                continue
            if c_id in claimed_by_courier:
                continue
            # Claim
            assignment.setdefault(c_id, []).append(j_id)
            claimed_jobs.add(j_id)
            claimed_by_courier.add(c_id)
            any_claim = True

        # Remove claimed jobs from remaining
        for j_id in claimed_jobs:
            remaining_job_ids.discard(j_id)

        if not any_claim:
            break

    # Filter out empty entries
    assignment = {cid: jids for cid, jids in assignment.items() if jids}
    return assignment
