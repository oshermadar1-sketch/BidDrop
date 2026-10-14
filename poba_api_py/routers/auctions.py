# app/routers/auctions.py
# Double-sided sealed-bid + quality scoring (price + driver rating + distance proxy).
# Persists assignments, updates bids/requests, and optionally stores a clearing_price in escrows.
# Comments in English.

from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
from uuid import UUID
import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from Backend.Database.db import get_db
from Backend.models import (
    User as UserModel,
    Request as RequestModel,
    Bid as BidModel,
    Assignment as AssignmentModel,
    Escrow as EscrowModel,   # for clearing_price (optional)
)

router = APIRouter(prefix="/auctions", tags=["auctions"])

# ---------------- DTOs ----------------
class ClearRequest(BaseModel):
    request_ids: Optional[List[UUID]] = None  # subset; else all OPEN

class ClearResponse(BaseModel):
    ok: bool
    assigned: Dict[str, str] = {}  # {request_id: driver_user_id}
    count: int = 0
    message: Optional[str] = None

# ---------------- Helpers ----------------

def _load_open_requests(db: Session, ids: Optional[List[UUID]] = None) -> List[RequestModel]:
    """Load OPEN requests of any type (ride or package)."""
    q = db.query(RequestModel).filter(RequestModel.status == "open")
    if ids:
        q = q.filter(RequestModel.id.in_(ids))
    return q.all()

def _load_revealed_bids(db: Session, request_ids: List[UUID]) -> List[BidModel]:
    if not request_ids:
        return []
    return (
        db.query(BidModel)
          .filter(BidModel.request_id.in_(request_ids))
          .filter(BidModel.status == "revealed")
          .all()
    )

def _is_driver(db: Session, user_id: UUID) -> bool:
    u = db.query(UserModel).filter(UserModel.id == user_id).first()
    return bool(u and getattr(u, "role", None) == "driver")

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    """Great-circle distance in KM; returns None if any coord missing."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    p = math.pi / 180.0
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = 0.5 - math.cos(dlat)/2 + math.cos(lat1*p)*math.cos(lat2*p)*(1 - math.cos(dlon))/2
    return 2 * R * math.asin(math.sqrt(a))

def _score_bid(
    db: Session,
    r: RequestModel,
    b: BidModel,
    w_price: float = 0.6,
    w_rating: float = 0.25,
    w_dist: float = 0.15,
) -> float:
    """
    Higher is better. Combines:
    - price (lower is better) -> inverse
    - driver rating (higher is better) -> rating/5
    - request distance proxy (shorter is better) -> inverse
    Works even if coords are missing (distance term becomes 0).
    """
    # price term
    price = float(b.revealed_amount)
    price_term = 1.0 / max(0.01, price)

    # rating term
    u = db.query(UserModel).filter(UserModel.id == b.bidder_user_id).first()
    rating = float(getattr(u, "rating", 0) or 0)  # 0..5
    rating_term = rating / 5.0

    # distance proxy (from -> to)
    dist_km = None
    if getattr(r, "from_lat", None) is not None and getattr(r, "from_lon", None) is not None \
       and getattr(r, "to_lat", None) is not None and getattr(r, "to_lon", None) is not None:
        dist_km = _haversine_km(float(r.from_lat), float(r.from_lon), float(r.to_lat), float(r.to_lon))
    dist_term = (1.0 / (dist_km + 0.1)) if (dist_km is not None) else 0.0

    return (w_price * price_term) + (w_rating * rating_term) + (w_dist * dist_term)

# ---------------- Winner selection (double auction + quality) ----------------

def _pick_winners(db: Session, reqs: List[RequestModel], bids: List[BidModel]) -> Dict[UUID, UUID]:
    """
    Double-sided + quality-aware:
    - Consider only bids where ask (revealed_amount) <= request.max_price (if set).
    - Score by price (inverse), driver rating, and request distance proxy.
    - Winner = highest score; tie-break: lower price, higher rating, earlier created_at.
    """
    # Group bids by request
    by_req: Dict[UUID, List[BidModel]] = {}
    for b in bids:
        by_req.setdefault(b.request_id, []).append(b)

    winners: Dict[UUID, UUID] = {}

    for r in reqs:
        r_bids = by_req.get(r.id, [])
        if not r_bids:
            continue

        candidates: List[tuple[float, BidModel, float, float]] = []  # (score, bid, price, rating)
        for b in r_bids:
            amt = getattr(b, "revealed_amount", None)
            if amt is None:
                continue
            # Double-auction constraint: ask ≤ max_price
            if r.max_price is not None and float(amt) > float(r.max_price):
                continue
            if not _is_driver(db, b.bidder_user_id):
                continue

            score = _score_bid(db, r, b, w_price=0.6, w_rating=0.25, w_dist=0.15)
            # get rating once for tie-breakers
            u = db.query(UserModel).filter(UserModel.id == b.bidder_user_id).first()
            rating = float(getattr(u, "rating", 0) or 0)
            candidates.append((score, b, float(amt), rating))

        if not candidates:
            continue

        # sort: score DESC, price ASC, rating DESC, created_at ASC
        def _tie_key(item):
            score, b, price, rating = item
            created_at = getattr(b, "created_at", 0)
            return (-score, price, -rating, created_at)

        candidates.sort(key=_tie_key)
        best_bid = candidates[0][1]
        winners[r.id] = best_bid.bidder_user_id

    return winners

# ---------------- Persistence (assignments/bids/requests + escrow) -----------

def _persist_results(db: Session, winners: Dict[UUID, UUID]) -> int:
    """
    Upsert assignments and update request/bid statuses.
    Also upsert escrow with a clearing_price (double auction policy).
    """
    created = 0
    now_dt = datetime.now(timezone.utc)

    for req_id, driver_id in winners.items():
        # Fetch request and winning bid
        r = db.query(RequestModel).filter(RequestModel.id == req_id).first()
        win_bid = (
            db.query(BidModel)
              .filter(BidModel.request_id == req_id, BidModel.bidder_user_id == driver_id)
              .first()
        )
        if not (r and win_bid and win_bid.revealed_amount is not None):
            continue

        ask = float(win_bid.revealed_amount)
        buyer_max = float(r.max_price or 0.0)

        # Double-auction clearing price policy:
        # Option A (fair midpoint): (ask + buyer_max) / 2
        # Option B (simple): ask
        clearing_price = (ask + buyer_max) / 2.0 if buyer_max > 0 else ask

        # Upsert assignment (one active per request)
        a = db.query(AssignmentModel).filter(AssignmentModel.request_id == req_id).first()
        if a:
            a.driver_user_id = driver_id
            a.status = "created"
            a.assigned_at = now_dt
        else:
            a = AssignmentModel(
                request_id=req_id,
                driver_user_id=driver_id,
                status="created",
                assigned_at=now_dt,
            )
            db.add(a)
            db.flush()  # ensure a.id exists for escrow FK

        # Update request status → assigned
        db.query(RequestModel).filter(RequestModel.id == req_id).update({"status": "assigned"})

        # Update bids: winner → won, others → lost
        all_bids = db.query(BidModel).filter(BidModel.request_id == req_id).all()
        for b in all_bids:
            if b.status in ("committed", "cancelled"):
                continue
            b.status = "won" if b.bidder_user_id == driver_id else "lost"

        # Upsert escrow with clearing_price
        esc = db.query(EscrowModel).filter(EscrowModel.assignment_id == a.id).first()
        if esc:
            esc.amount = clearing_price
        else:
            db.add(EscrowModel(assignment_id=a.id, amount=clearing_price))

        created += 1

    db.commit()
    return created

# ---------------- Endpoints ----------------

@router.post("/clear", response_model=ClearResponse)
def clear(payload: ClearRequest, db: Session = Depends(get_db)):
    # 1) Load open requests (optionally filtered by IDs)
    reqs = _load_open_requests(db, payload.request_ids)
    if not reqs:
        return ClearResponse(ok=True, assigned={}, count=0, message="NO_MATCH")

    # 2) Load revealed bids for these requests
    bids = _load_revealed_bids(db, [r.id for r in reqs])
    if not bids:
        return ClearResponse(ok=True, assigned={}, count=0, message="NO_MATCH")

    # 3) Pick winners (double auction + quality scoring)
    winners = _pick_winners(db, reqs, bids)
    if not winners:
        return ClearResponse(ok=True, assigned={}, count=0, message="NO_MATCH")

    # 4) Persist results
    count = _persist_results(db, winners)

    # 5) Response mapping as strings (UUID → str)
    assigned_str = {str(k): str(v) for k, v in winners.items()}
    return ClearResponse(ok=True, assigned=assigned_str, count=count)
