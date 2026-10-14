# routes_sender.py
# Sender dashboard API: metrics and request listing for the logged-in user.
# Relies on JWT auth (auth_dep.get_current_user) and your 'requests' + 'assignments' tables.
#
# NOTE:
#   list_requests now LEFT JOINs assignments to expose:
#     - max_price  (sender's maximum willingness to pay, from requests.max_price)
#     - agreed_price (final matched price, from assignments.agreed_price_cents / 100.0)
#   The mobile app can use agreed_price when it exists, and fall back to max_price.

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any

from .Database.db import get_db
from .auth_dep import get_current_user  # returns dict of current user (incl. id)

router = APIRouter(prefix="/sender", tags=["sender"])

# ---- CONFIG: which request.type values are considered "sender" requests ----
# Adjust if your schema uses different names (e.g. 'delivery', 'parcel' etc.)
SENDER_TYPES: List[str] = ["package"]


def _status_bucket_to_sql_list(bucket: str) -> List[str]:
    """
    Map UI buckets to underlying request.status values.
      - open      -> ['open']
      - active    -> ['assigned', 'in_transit']
      - delivered -> ['completed']
    """
    bucket = (bucket or "").lower()
    if bucket == "open":
        return ["open"]
    if bucket == "active":
        return ["assigned", "in_transit"]
    if bucket == "delivered":
        return ["completed"]
    raise HTTPException(status_code=400, detail="Invalid status bucket")


@router.get("/metrics")
def sender_metrics(
    db: Session = Depends(get_db),
    me: Dict[str, Any] = Depends(get_current_user),
):
    """
    Return counts for the sender's requests grouped into UI buckets.
    Only counts requests that belong to the SENDER_TYPES.
    """
    uid = me["id"]

    # Build placeholders for IN (...) on type
    type_placeholders = ", ".join(f":t{i}" for i in range(len(SENDER_TYPES)))
    type_params = {f"t{i}": t for i, t in enumerate(SENDER_TYPES)}

    rows = db.execute(
        text(f"""
            SELECT status, COUNT(*) AS cnt
            FROM requests
            WHERE owner_user_id = :uid
              AND type IN ({type_placeholders})
            GROUP BY status
        """),
        {"uid": uid, **type_params},
    ).mappings().all()

    by_status = {r["status"]: int(r["cnt"]) for r in rows}

    open_count = by_status.get("open", 0)
    active_count = by_status.get("assigned", 0) + by_status.get("in_transit", 0)
    delivered_count = by_status.get("completed", 0)
    cancelled_count = by_status.get("cancelled", 0)

    return {
        "open_count": open_count,
        "active_count": active_count,
        "delivered_count": delivered_count,
        "cancelled_count": cancelled_count,  # spare for future UI
    }


@router.get("/requests")
def list_requests(
    status: str = Query("open", description="open | active | delivered"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    me: Dict[str, Any] = Depends(get_current_user),
):
    """
    List the current user's *sender* requests filtered by a UI bucket.
    Returns only rows with type in SENDER_TYPES.

    Additionally:
      - max_price is returned from requests.max_price (numeric).
      - agreed_price is returned from assignments.agreed_price_cents / 100.0
        (LEFT JOIN; may be NULL if no assignment exists yet).
    """
    uid = me["id"]
    statuses = _status_bucket_to_sql_list(status)

    # Build placeholders for IN (...) on status and type
    status_placeholders = ", ".join(f":s{i}" for i in range(len(statuses)))
    type_placeholders = ", ".join(f":t{i}" for i in range(len(SENDER_TYPES)))

    params = {
        "uid": uid,
        "limit": limit,
        "offset": offset,
        **{f"s{i}": s for i, s in enumerate(statuses)},
        **{f"t{i}": t for i, t in enumerate(SENDER_TYPES)},
    }

    # We LEFT JOIN assignments to expose agreed_price_cents when there is an assignment.
    # We aggregate with MAX() assuming at most one relevant assignment per request.
    rows = db.execute(
        text(f"""
            SELECT
                r.id::text            AS id,
                r.owner_user_id::text AS owner_user_id,
                r.type::text          AS type,
                r.from_address,
                r.from_lat,
                r.from_lon,
                r.to_address,
                r.to_lat,
                r.to_lon,
                r.passengers,
                r.notes,
                r.window_start,
                r.window_end,
                r.status::text        AS status,
                r.max_price::numeric  AS max_price,
                MAX(a.agreed_price_cents)::numeric / 100.0 AS agreed_price,
                r.created_at,
                r.updated_at
            FROM requests r
            LEFT JOIN assignments a
              ON a.request_id = r.id
             AND a.status IN ('created','picked_up','in_transit','completed')
            WHERE r.owner_user_id = :uid
              AND r.type IN ({type_placeholders})
              AND r.status IN ({status_placeholders})
            GROUP BY
                r.id,
                r.owner_user_id,
                r.type,
                r.from_address,
                r.from_lat,
                r.from_lon,
                r.to_address,
                r.to_lat,
                r.to_lon,
                r.passengers,
                r.notes,
                r.window_start,
                r.window_end,
                r.status,
                r.max_price,
                r.created_at,
                r.updated_at
            ORDER BY r.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).mappings().all()

    return [dict(r) for r in rows]
