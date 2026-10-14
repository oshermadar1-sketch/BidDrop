# services/courier_trust.py
# Loads a courier's history from the DB and computes the trust score (see trust_score.py).
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..ml_predictor import features_for_request, predict_delivery_rating, predict_delivery_time
from ..models import Assignment, Rating, Request
from ..trust_score import calculate_trust_score

# A delivery finished in less than this share of the predicted time is not realistic
# (e.g. "delivered" pressed without delivering); it is skipped instead of earning full points.
MIN_REALISTIC_SHARE = 1 / 3

# Ranking of couriers for a request: mostly how trustworthy, partly how fast (see match_score).
MATCH_TRUST_WEIGHT = 0.7
MATCH_SPEED_WEIGHT = 0.3


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def delivery_model_score(asn: Assignment, req: Request) -> Optional[float]:
    """
    ML score (1..5) of one completed delivery, or None if it cannot be timed: model 2's
    expected customer rating for how long it took compared with model 1's prediction.
    Actual time: from when the courier could start (assignment time, or the request's
    window start if later) until completion. Predicted time: the ML model for the same
    route, day, weather and traffic, with a typical courier, so every courier is judged
    against the same yardstick.
    Deliveries that cannot be timed, or that were suspiciously fast (under
    MIN_REALISTIC_SHARE of the prediction), return None and are not counted.
    """
    completed = _utc(asn.completed_at)
    start = _utc(asn.assigned_at)
    window_start = _utc(getattr(req, "window_start", None))
    if window_start and start and window_start > start:
        start = window_start
    if not completed or not start or completed <= start:
        return None

    actual_min = (completed - start).total_seconds() / 60
    predicted_min = predict_delivery_time(features_for_request(req, when=start))
    if actual_min < predicted_min * MIN_REALISTIC_SHARE:
        return None
    return predict_delivery_rating(predicted_min, actual_min)


def get_courier_trust(db: Session, user_id) -> dict:
    count, avg = (
        db.query(func.count(Rating.id), func.avg(Rating.score))
        .filter(Rating.ratee_user_id == user_id)
        .one()
    )

    rows = (
        db.query(Assignment, Request)
        .join(Request, Request.id == Assignment.request_id)
        .filter(
            Assignment.driver_user_id == user_id,
            Assignment.status == "completed",
        )
        .all()
    )
    scores = [p for p in (delivery_model_score(a, r) for a, r in rows) if p is not None]

    return calculate_trust_score(
        avg_rating=float(avg) if avg is not None else None,
        num_ratings=count or 0,
        delivery_scores=scores,
    )


def predicted_minutes_for_offer(req: Request, offer, courier_rating=None, courier=None) -> float:
    """
    Predicted minutes for this courier: from the offer's start point to pickup, then the trip,
    with the courier's age and vehicle when their profile has them.
    """
    return predict_delivery_time(features_for_request(
        req,
        courier_rating=courier_rating,
        courier_lat=getattr(offer, "from_lat", None),
        courier_lon=getattr(offer, "from_lon", None),
        courier=courier,
    ))


def match_score(trust_score: float, predicted_min: float, fastest_min: float) -> float:
    """
    0..1, higher is better. Both parts are on a 0..1 scale:
    trust 1..5 -> /5; speed = fastest predicted time among candidates / this courier's time.
    """
    speed = fastest_min / predicted_min if predicted_min > 0 else 1.0
    return MATCH_TRUST_WEIGHT * (trust_score / 5) + MATCH_SPEED_WEIGHT * speed
