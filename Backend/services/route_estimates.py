# Backend/services/route_estimates.py
# Stores the road distance, driving time and estimated arrival of an assignment.
#
# The estimate is the pickup -> drop-off driving time from the routing service, counted
# from the later of "now" and the request's window start when the assignment is created,
# and recounted from the moment the courier picks up. It is a route-based estimate; the
# learned delivery-time prediction (predicted_minutes) stays separate.
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import routing

log = logging.getLogger("route_estimates")


def leg_for_coords(from_lat, from_lon, to_lat, to_lon) -> Optional[routing.RouteLeg]:
    if None in (from_lat, from_lon, to_lat, to_lon):
        return None
    return routing.leg(float(from_lat), float(from_lon), float(to_lat), float(to_lon))


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def stamp_assignment_estimate(db: Session, request_id: str) -> Optional[datetime]:
    """
    Fill route_distance_km, route_duration_min and estimated_arrival_at on the
    assignment of `request_id`. Never raises: a routing problem must not block an
    assignment, so the columns just stay NULL.
    """
    try:
        row = db.execute(text("""
            SELECT a.id AS assignment_id, r.from_lat, r.from_lon, r.to_lat, r.to_lon, r.window_start
            FROM assignments a
            JOIN requests r ON r.id = a.request_id
            WHERE a.request_id = CAST(:rid AS uuid)
        """), {"rid": str(request_id)}).mappings().first()
        if not row:
            return None
        est = leg_for_coords(row["from_lat"], row["from_lon"], row["to_lat"], row["to_lon"])
        if est is None:
            return None
        now = datetime.now(timezone.utc)
        start = _as_utc(row["window_start"])
        start = max(now, start) if start else now
        arrival = start + timedelta(minutes=est.duration_min)
        db.execute(text("""
            UPDATE assignments
            SET route_distance_km = :km, route_duration_min = :mins, estimated_arrival_at = :eta
            WHERE id = :aid
        """), {"km": round(est.distance_km, 3), "mins": round(est.duration_min, 1),
               "eta": arrival, "aid": row["assignment_id"]})
        return arrival
    except Exception as e:
        log.warning("Could not store the route estimate for request %s: %s", request_id, e)
        return None
