# services/matching.py
# Matching logic with proper row-level locking and UTC timestamps.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# ORM models (single source of truth)
from ..models import Assignment, Request  # aliases exist in models.py
# Prefer CourierOffer; fall back to Offer if your project uses that name.
try:
    from ..models import CourierOffer
except Exception:  # pragma: no cover
    from ..models import Offer as CourierOffer  # type: ignore

from .courier_trust import get_courier_trust, match_score, predicted_minutes_for_offer

# ---- Status constants aligned with your enums ----
REQ_OPEN = "open"
REQ_ASSIGNED = "assigned"

OFFER_ACTIVE = "active"
OFFER_ASSIGNED = "assigned"

ASSN_CREATED = "created"
ACTIVE_ASSIGNMENT_STATUSES = {"created", "picked_up", "in_transit"}

def _price_to_cents(value):
    if value is None:
        return 0
    return int(float(value) * 100)


# --------- Time window helper ----------
def _time_overlaps(a_start, a_end, b_start, b_end) -> bool:
    """
    Basic time-window overlap check.
    If any side is None (no window), treat as unbounded/overlapping.
    """
    if not a_start or not a_end or not b_start or not b_end:
        return True
    return max(a_start, b_start) <= min(a_end, b_end)


# --------- Core predicate: request matches offer ----------
def _request_matches_offer(req: Request, off: CourierOffer) -> bool:
    """
    Adjust to your domain fields if you add constraints (distance, budget, etc.).
    Currently:
    - Treat 'ride' and 'passenger' equivalently on the UI. DB types are literal.
    - Time-window overlap is required if both sides have windows.
    - Type compatibility:
        If offer.types is an array, require req.type to be included.
        If offer has a single 'type' column in your schema, just compare strings.
    """
    # If offer has 'types' ARRAY (as in our models), use membership:
    if hasattr(off, "types") and off.types:
        if str(req.type) not in [str(t) for t in off.types]:
            return False
    else:
        # Fallback: single-typed offer
        if getattr(off, "type", None) and str(req.type) != str(off.type):
            return False

    # Time overlap
    if not _time_overlaps(
        getattr(req, "window_start", None),
        getattr(req, "window_end", None),
        getattr(off, "window_start", None),
        getattr(off, "window_end", None),
    ):
        return False

    return True


# --------- Transactional matching (driver-first) ---------
def match_for_offer(session: Session, *, offer_id: str) -> Optional[Assignment]:
    """
    Driver flow: we have an ACTIVE CourierOffer.
    Atomically pick ONE OPEN request that matches and create an Assignment.
    Returns the Assignment or None if no match (or race lost).
    """
    with session.begin():  # atomic transaction
        offer = (
            session.query(CourierOffer)
            .filter(CourierOffer.id == offer_id, CourierOffer.status == OFFER_ACTIVE)
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        if not offer:
            return None  # not found / not active

        # Lock candidate OPEN requests (you can replace with a ranked query)
        candidates = (
            session.query(Request)
            .filter(Request.status == REQ_OPEN)
            .with_for_update(skip_locked=True)
            .all()
        )

        chosen: Optional[Request] = None
        for r in candidates:
          if _request_matches_offer(r, offer):
            chosen = r
            break

        if not chosen:
             return None

        asn = Assignment(
            request_id=chosen.id,
            driver_user_id=offer.driver_user_id,
            offer_id=getattr(offer, "id", None),
            agreed_price_cents=_price_to_cents(getattr(offer, "min_price", None)),
            status=ASSN_CREATED,
            assigned_at=datetime.now(timezone.utc),
        )
        session.add(asn)

        chosen.status = REQ_ASSIGNED
        offer.status = OFFER_ASSIGNED

        try:
            session.flush()  # let DB constraints protect us
        except IntegrityError as e:
            print("MATCHING DB ERROR:", e)
            session.rollback()
            return None

        return asn


# --------- Transactional matching (request-first) ---------
def match_for_request(session: Session, *, request_id: str) -> Optional[Assignment]:
    """
    Sender/Rider flow: we have an OPEN Request.
    Atomically pick ONE ACTIVE CourierOffer that matches and create an Assignment.
    Returns the Assignment or None if no match (or race lost).
    """
    with session.begin():
        req = (
            session.query(Request)
            .filter(Request.id == request_id, Request.status == REQ_OPEN)
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        if not req:
            return None

        offers = (
            session.query(CourierOffer)
            .filter(CourierOffer.status == OFFER_ACTIVE)
            .with_for_update(skip_locked=True)
            .all()
        )

        valid_offers = [off for off in offers if _request_matches_offer(req, off)]

        # Rank couriers by trust score (customers + ML punctuality) and ML-predicted time.
        trust_by_driver = {}
        minutes_by_offer = {}
        for off in valid_offers:
            if off.driver_user_id not in trust_by_driver:
                trust_by_driver[off.driver_user_id] = get_courier_trust(session, off.driver_user_id)["trust_score"]
            minutes_by_offer[off.id] = predicted_minutes_for_offer(
                req, off,
                courier_rating=off.driver.rating if off.driver else None,
                courier=off.driver,
            )

        if valid_offers:
            fastest = min(minutes_by_offer.values())
            valid_offers.sort(
                key=lambda off: match_score(
                    trust_by_driver[off.driver_user_id], minutes_by_offer[off.id], fastest
                ),
                reverse=True,
            )

        chosen = valid_offers[0] if valid_offers else None

        if not chosen:
            return None

        asn = Assignment(
            request_id=req.id,
            driver_user_id=chosen.driver_user_id,
            offer_id=getattr(chosen, "id", None),
            agreed_price_cents=_price_to_cents(getattr(chosen, "min_price", None)),
            status=ASSN_CREATED,
            assigned_at=datetime.now(timezone.utc),
        )
        session.add(asn)

        req.status = REQ_ASSIGNED
        chosen.status = OFFER_ASSIGNED

        try:
            session.flush()
        except IntegrityError as e:
            print("MATCHING DB ERROR:", e)
            session.rollback()
            return None

        return asn
