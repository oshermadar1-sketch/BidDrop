# routes_matching.py
# Router that exposes matching operations. Comments in English; Hebrew responses for the app.

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .Database.db import get_db
from .services.matching import match_for_offer, match_for_request

router = APIRouter(prefix="/match", tags=["matching"])

@router.post("/offers/{offer_id}/run")
def run_matching_for_offer(offer_id: str, db: Session = Depends(get_db)):
    """
    Driver pressed "find me a task": attempt to create a real Assignment.
    Returns a Hebrew message and IDs only if the assignment was truly created.
    """
    asn = match_for_offer(db, offer_id=offer_id)
    if not asn:
        # No feasible request OR race lost. We return a soft Hebrew message.
        return {"status": "no_match", "message": "אין התאמה כרגע עבור ההצעה הזו"}
    return {
        "status": "matched",
        "message": "נמצאה משימה והוקצה שיוך",
        "assignment_id": str(asn.id),
        "request_id": str(asn.request_id),
    }


@router.post("/requests/{request_id}/run")
def run_matching_for_request(request_id: str, db: Session = Depends(get_db)):
    """
    Sender/Rider pressed "find me a driver": attempt to create a real Assignment.
    Returns a Hebrew message and IDs only if the assignment was truly created.
    """
    asn = match_for_request(db, request_id=request_id)
    if not asn:
        return {"status": "no_match", "message": "אין זמינות נהגים מתאימה כרגע"}
    return {
        "status": "matched",
        "message": "נמצא נהג והוקצה שיוך",
        "assignment_id": str(asn.id),
        "request_id": str(asn.request_id),
    }
