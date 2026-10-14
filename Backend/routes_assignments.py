# Backend/routes_assignments.py
# Assignment details + status updates. Always return tz-aware datetimes.

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .Database.db import get_db
from .models import Assignment, User, Request, Escrow, Rating, CourierOffer
from .services.courier_trust import get_courier_trust, predicted_minutes_for_offer
# Optional live locations model
try:
    from .models import CourierLocation
    HAS_LOCATIONS = True
except Exception:
    HAS_LOCATIONS = False
    CourierLocation = None  # type: ignore

logger = logging.getLogger("assignments")

# -------------------------- Schemas --------------------------

class DriverBrief(BaseModel):
    id: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    rating: Optional[float] = None
    vehicle_type: Optional[str] = None
    avatar_url: Optional[str] = None
    # Trust score 1..5 (customers + ML punctuality, see trust_score.py)
    trust_score: Optional[float] = None
    num_ratings: Optional[int] = None
    is_new_courier: Optional[bool] = None
    # How the trust score was computed ("how is the score calculated?" in the app)
    customer_part: Optional[float] = None
    model_part: Optional[float] = None
    customer_weight: Optional[float] = None
    model_weight: Optional[float] = None
    num_timed_deliveries: Optional[int] = None


class RequesterBrief(BaseModel):
    id: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    rating: Optional[float] = None
    avatar_url: Optional[str] = None


class LastLocation(BaseModel):
    lat: float
    lng: float
    updated_at: datetime


class RequestBrief(BaseModel):
    id: str
    type: str  # "package" | "ride" | "passenger"
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    passengers: Optional[int] = None
    pickup_contact_name: Optional[str] = None
    pickup_contact_phone: Optional[str] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    notes: Optional[str] = None


class AssignmentDetailOut(BaseModel):
    assignment_id: str
    request_id: str
    status: str
    # Payment status + agreed price
    payment_status: Optional[str] = None
    agreed_price_cents: Optional[int] = None

    assigned_at: datetime
    picked_up_at: Optional[datetime] = None
    in_transit_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    onchain_tx_hash: Optional[str] = None

    driver: DriverBrief
    requester: Optional[RequesterBrief] = None
    last_location: Optional[LastLocation] = None
    request: RequestBrief

    # ML-predicted delivery time for this courier and route (minutes)
    predicted_minutes: Optional[float] = None
    # Score the customer gave the driver for this assignment (None = not rated yet)
    driver_rating_score: Optional[int] = None


# Input model for status update
class AssignmentStatusUpdateIn(BaseModel):
    status: str


# ------------------------------ Router ------------------------------

router = APIRouter(prefix="/assignments", tags=["assignments"])

# Active assignment statuses used by "by-request"
# IMPORTANT: include "completed" so that sender/rider can still see details
# after the driver marked the assignment as completed.
ACTIVE_ASSIGNMENT_STATUSES = {"created", "picked_up", "in_transit", "completed"}

# Allowed logistics status transitions for assignments
ALLOWED_STATUS_TRANSITIONS = {
    "created": {"picked_up", "cancelled", "failed"},
    "picked_up": {"in_transit", "cancelled", "failed"},
    "in_transit": {"completed", "cancelled", "failed"},
    "completed": set(),
    "cancelled": set(),
    "failed": set(),
}
VALID_ASSIGNMENT_STATUSES = set(ALLOWED_STATUS_TRANSITIONS.keys())


def _normalize_request_type(v: Optional[str]) -> str:
    """Normalize request type field coming from DB."""
    s = (v or "").strip().lower()
    if s in {"package", "ride", "passenger"}:
        return s
    if s == "rider":
        return "ride"
    return "package"


def _ensure_tz(dt: Optional[datetime]) -> Optional[datetime]:
    """Return tz-aware datetime (UTC) or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _pack_assignment_detail(db: Session, assignment: Assignment) -> AssignmentDetailOut:
    """Build a rich, mobile-friendly assignment payload."""

    # ---- Driver
    driver = db.query(User).filter(User.id == assignment.driver_user_id).first()
    if not driver:
        raise HTTPException(status_code=500, detail="Driver user missing")

    full_name = f"{getattr(driver, 'first_name', '') or ''} {getattr(driver, 'last_name', '') or ''}".strip() or None
    try:
        rating_val = float(driver.rating) if driver.rating is not None else None
    except Exception:
        rating_val = None

    try:
        trust = get_courier_trust(db, driver.id)
    except Exception as e:  # never fail the details screen because of the score
        logger.warning("Trust score failed for driver %s: %s", driver.id, e)
        trust = {}

    driver_out = DriverBrief(
        id=str(driver.id),
        full_name=full_name,
        phone=getattr(driver, "phone", None),
        rating=rating_val,
        vehicle_type=getattr(driver, "vehicle_type", None),
        avatar_url=getattr(driver, "avatar_url", None),
        trust_score=trust.get("trust_score"),
        num_ratings=trust.get("num_ratings"),
        is_new_courier=trust.get("is_new_courier"),
        customer_part=trust.get("customer_part"),
        model_part=trust.get("model_part"),
        customer_weight=trust.get("customer_weight"),
        model_weight=trust.get("model_weight"),
        num_timed_deliveries=trust.get("num_timed_deliveries"),
    )

    # ---- Request
    req = db.query(Request).filter(Request.id == assignment.request_id).first()
    if not req:
        raise HTTPException(status_code=500, detail="Request row missing")

    request_out = RequestBrief(
        id=str(req.id),
        type=_normalize_request_type(getattr(req, "type", None)),
        from_address=getattr(req, "from_address", None),
        to_address=getattr(req, "to_address", None),
        passengers=getattr(req, "passengers", None),
        pickup_contact_name=getattr(req, "pickup_contact_name", None),
        pickup_contact_phone=getattr(req, "pickup_contact_phone", None),
        window_start=_ensure_tz(getattr(req, "window_start", None)),
        window_end=_ensure_tz(getattr(req, "window_end", None)),
        notes=getattr(req, "notes", None),
    )

    # ---- Request owner (requester)
    requester_out: Optional[RequesterBrief] = None
    owner_id = getattr(req, "owner_user_id", None)
    if owner_id:
        requester = db.query(User).filter(User.id == owner_id).first()
        if requester:
            rn = f"{getattr(requester, 'first_name', '') or ''} {getattr(requester, 'last_name', '') or ''}".strip() or None
            try:
                r_rating = float(requester.rating) if requester.rating is not None else None
            except Exception:
                r_rating = None
            requester_out = RequesterBrief(
                id=str(requester.id),
                full_name=rn,
                phone=getattr(requester, "phone", None),
                rating=r_rating,
                avatar_url=getattr(requester, "avatar_url", None),
            )

    # ---- Last known location (optional)
    last_loc: Optional[LastLocation] = None
    if HAS_LOCATIONS:
        loc = (
            db.query(CourierLocation)
            .filter(CourierLocation.user_id == driver.id)
            .order_by(CourierLocation.updated_at.desc())
            .first()
        )
        if loc:
            try:
                last_loc = LastLocation(
                    lat=float(loc.lat),
                    lng=float(loc.lng),
                    updated_at=_ensure_tz(loc.updated_at) or datetime.now(timezone.utc),
                )
            except Exception:
                last_loc = None

    # ---- Assigned time with tz fallback (heals old naive rows)
    assigned_at = (
        assignment.assigned_at
        or getattr(assignment, "created_at", None)
        or getattr(assignment, "updated_at", None)
    )
    if not assigned_at:
        assigned_at = datetime.now(timezone.utc)
    if assigned_at.tzinfo is None:
        assigned_at = assigned_at.replace(tzinfo=timezone.utc)

    # Normalize payment status
    ps = getattr(assignment, "payment_status", None)
    ps_str = str(ps) if ps is not None else None

    # Normalize price cents
    price_cents: Optional[int]
    try:
        price_cents = (
            int(getattr(assignment, "agreed_price_cents", 0))
            if assignment.agreed_price_cents is not None
            else None
        )
    except Exception:
        price_cents = None

    # ---- ML-predicted delivery time (from the courier's offer start point when known)
    predicted_minutes: Optional[float] = None
    try:
        offer = (
            db.query(CourierOffer).filter(CourierOffer.id == assignment.offer_id).first()
            if getattr(assignment, "offer_id", None) else None
        )
        predicted_minutes = round(
            predicted_minutes_for_offer(req, offer, courier_rating=rating_val, courier=driver)
        )
    except Exception as e:
        logger.warning("Delivery-time prediction failed for assignment %s: %s", assignment.id, e)

    existing_rating = db.query(Rating).filter(Rating.assignment_id == assignment.id).first()

    return AssignmentDetailOut(
        assignment_id=str(assignment.id),
        request_id=str(assignment.request_id),
        status=str(assignment.status),
        payment_status=ps_str,
        agreed_price_cents=price_cents,
        assigned_at=assigned_at,
        picked_up_at=_ensure_tz(getattr(assignment, "picked_up_at", None)),
        in_transit_at=_ensure_tz(getattr(assignment, "in_transit_at", None)),
        completed_at=_ensure_tz(getattr(assignment, "completed_at", None)),
        failed_at=_ensure_tz(getattr(assignment, "failed_at", None)),
        cancelled_at=_ensure_tz(getattr(assignment, "cancelled_at", None)),
        onchain_tx_hash=getattr(assignment, "onchain_tx_hash", None),
        driver=driver_out,
        requester=requester_out,
        last_location=last_loc,
        request=request_out,
        predicted_minutes=predicted_minutes,
        driver_rating_score=existing_rating.score if existing_rating else None,
    )


# ----------------------------- Endpoints -----------------------------

@router.get("/by-request/{request_id}", response_model=AssignmentDetailOut)
def get_assignment_by_request(
    request_id: str,
    db: Session = Depends(get_db),
    only_active: bool = Query(True, description="Return only non-cancelled/non-failed assignments"),
):
    """
    Fetch the (most recent) assignment for a given request.

    By default we restrict to "active-like" statuses:
      created, picked_up, in_transit, completed
    (we exclude cancelled / failed).

    This is important so that:
      - the driver can see details during the job
      - the sender/rider can still see details even after the driver marked
        the assignment as completed.
    """
    q = db.query(Assignment).filter(Assignment.request_id == request_id)
    if only_active:
        q = q.filter(Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES))
    assignment = q.order_by(Assignment.assigned_at.desc()).first()
    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="No assignment found for this request",
        )
    return _pack_assignment_detail(db, assignment)


@router.get("/{assignment_id}", response_model=AssignmentDetailOut)
def get_assignment_by_id(assignment_id: str, db: Session = Depends(get_db)):
    """
    Fetch a single assignment by its ID.
    """
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return _pack_assignment_detail(db, assignment)


# ------------------------- Update status endpoint -------------------------

@router.patch("/{assignment_id}/status", response_model=AssignmentDetailOut)
def update_assignment_status(
    assignment_id: str,
    payload: AssignmentStatusUpdateIn,
    db: Session = Depends(get_db),
):
    """
    Update the logistics status of an assignment and stamp the relevant milestone timestamp.

    Allowed status transitions:
      created    → picked_up / cancelled / failed
      picked_up  → in_transit / cancelled / failed
      in_transit → completed / cancelled / failed

    Once in completed / cancelled / failed, no further transitions are allowed.

    When status becomes 'completed' and an Escrow exists for this assignment,
    we also:
      - set escrows.driver_marked_completed_at = now (if empty)
      - set escrows.auto_release_at = now + 24h (if empty)
    The actual release/refund is handled by routes_escrow.py.
    """
    new_status = (payload.status or "").strip()
    if new_status not in VALID_ASSIGNMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid assignment status")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    current_status = str(assignment.status)
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())

    # No-op if same status
    if new_status == current_status:
        return _pack_assignment_detail(db, assignment)

    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Illegal status transition: {current_status} → {new_status}",
        )

    now = datetime.now(timezone.utc)

    # Stamp the relevant milestone timestamp once
    if new_status == "picked_up" and getattr(assignment, "picked_up_at", None) is None:
        assignment.picked_up_at = now
    elif new_status == "in_transit" and getattr(assignment, "in_transit_at", None) is None:
        assignment.in_transit_at = now
    elif new_status == "completed" and getattr(assignment, "completed_at", None) is None:
        assignment.completed_at = now
    elif new_status == "failed" and getattr(assignment, "failed_at", None) is None:
        assignment.failed_at = now
    elif new_status == "cancelled" and getattr(assignment, "cancelled_at", None) is None:
        assignment.cancelled_at = now

    assignment.status = new_status

    # --- Escrow side: driver marked completed + 24h auto-release window ---
    if (
        new_status == "completed"
        and getattr(assignment, "escrow", None) is not None
    ):
        esc = assignment.escrow
        # Mark when driver said "completed"
        if getattr(esc, "driver_marked_completed_at", None) is None:
            esc.driver_marked_completed_at = now
        # Start 24h countdown (only once)
        if getattr(esc, "auto_release_at", None) is None:
            esc.auto_release_at = now + timedelta(hours=24)
        db.add(esc)

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return _pack_assignment_detail(db, assignment)


# -------- Debug: recent --------

class RecentMatchItem(BaseModel):
    assignment_id: str
    request_id: str
    driver_user_id: str
    assigned_at: datetime
    status: str
    # Optional fields for debugging:
    payment_status: Optional[str] = None
    agreed_price_cents: Optional[int] = None

    request_type: Optional[str] = None
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    requester_name: Optional[str] = None
    driver_name: Optional[str] = None


@router.get("/recent", response_model=List[RecentMatchItem])
def list_recent_matches(limit: int = 50, db: Session = Depends(get_db)):
    """
    Debug endpoint: list recent assignments with basic request/driver info.
    """
    limit = max(1, min(limit, 200))
    rows = (
        db.query(Assignment, Request, User)
        .join(Request, Request.id == Assignment.request_id)
        .join(User, User.id == Assignment.driver_user_id)
        .order_by(Assignment.assigned_at.desc())
        .limit(limit)
        .all()
    )

    out: list[RecentMatchItem] = []
    for a, req, driver in rows:
        requester_name = None
        if getattr(req, "owner_user_id", None):
            rq = db.query(User).filter(User.id == req.owner_user_id).first()
            if rq:
                requester_name = (
                    f"{getattr(rq, 'first_name', '') or ''} {getattr(rq, 'last_name', '') or ''}".strip()
                    or None
                )

        driver_name = (
            f"{getattr(driver, 'first_name', '') or ''} {getattr(driver, 'last_name', '') or ''}".strip()
            or None
        )

        ps = getattr(a, "payment_status", None)
        ps_str = str(ps) if ps is not None else None
        try:
            price_cents = (
                int(getattr(a, "agreed_price_cents", 0))
                if a.agreed_price_cents is not None
                else None
            )
        except Exception:
            price_cents = None

        out.append(
            RecentMatchItem(
                assignment_id=str(a.id),
                request_id=str(a.request_id),
                driver_user_id=str(a.driver_user_id),
                assigned_at=_ensure_tz(a.assigned_at) or datetime.now(timezone.utc),
                status=str(a.status),
                payment_status=ps_str,
                agreed_price_cents=price_cents,
                request_type=_normalize_request_type(getattr(req, "type", None)),
                from_address=getattr(req, "from_address", None),
                to_address=getattr(req, "to_address", None),
                requester_name=requester_name,
                driver_name=driver_name,
            )
        )
    return out


# ---------------------- Confirm delivered (sender/rider) ----------------------

@router.post("/{assignment_id}/confirm-delivered", response_model=AssignmentDetailOut)
def confirm_assignment_delivered(
    assignment_id: str,
    db: Session = Depends(get_db),
):
    """
    Called by the sender / rider when הם מאשרים שהחבילה/הנסיעה הסתיימה בהצלחה.

    לוגיקה:
      - מאתרים את ה-assignment לפי id.
      - מאתרים את ה-escrow (דרך הקשר או לפי assignment_id).
      - מסמנים שהלקוח אישר קבלה (sender_marked_received_at = now).
      - אם הסטטוס של ה-escrow עדיין לא סופי, משחררים אותו (status='released'),
        מנקים auto_release_at, ומעדכנים released_at אם קיים.
      - מחזירים שוב AssignmentDetailOut מעודכן.
    """
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Try to get escrow via relationship
    esc = getattr(assignment, "escrow", None)

    # Fallback: manual query by assignment_id
    if esc is None:
        esc = (
            db.query(Escrow)
            .filter(Escrow.assignment_id == assignment.id)
            .first()
        )

    # If there is no escrow at all, nothing to release – just return details
    if esc is None:
        return _pack_assignment_detail(db, assignment)

    now = datetime.now(timezone.utc)

    # Mark that the customer confirmed delivery
    if getattr(esc, "sender_marked_received_at", None) is None:
        esc.sender_marked_received_at = now

    # If escrow is not in a terminal state, release it now
    term_statuses = {"released", "refunded", "cancelled", "failed"}
    current_status = str(getattr(esc, "status", "") or "").lower()

    if current_status not in term_statuses:
        esc.status = "released"

        # Optional fields if exist on model:
        if hasattr(esc, "released_at") and getattr(esc, "released_at", None) is None:
            esc.released_at = now
        if hasattr(esc, "auto_release_at"):
            esc.auto_release_at = None

    db.add(esc)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return _pack_assignment_detail(db, assignment)

class RatingIn(BaseModel):
    score: int
    comment: Optional[str] = None

@router.post("/{assignment_id}/rate-driver")
def rate_driver(
    assignment_id: str,
    payload: RatingIn,
    db: Session = Depends(get_db),
):
    if payload.score < 1 or payload.score > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if str(assignment.status) != "completed":
        raise HTTPException(status_code=400, detail="Assignment must be completed before rating")

    existing = db.query(Rating).filter(Rating.assignment_id == assignment.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Assignment already rated")

    new_rating = Rating(
        rater_user_id=assignment.request.owner_user_id,
        ratee_user_id=assignment.driver_user_id,
        assignment_id=assignment.id,
        score=payload.score,
        comment=payload.comment,
    )

    db.add(new_rating)
    db.flush()

    ratings = db.query(Rating).filter(Rating.ratee_user_id == assignment.driver_user_id).all()
    avg_rating = sum(r.score for r in ratings) / len(ratings)

    driver = db.query(User).filter(User.id == assignment.driver_user_id).first()
    if driver:
        driver.rating = avg_rating

    db.commit()

    return {
        "status": "rated",
        "assignment_id": assignment_id,
        "driver_user_id": str(assignment.driver_user_id),
        "new_rating": round(avg_rating, 2),
    }