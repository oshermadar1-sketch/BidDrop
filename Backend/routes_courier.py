# routes_courier.py
# FastAPI routes for "Courier" (driver) dashboard using SQL text().
# Endpoints:
#   GET  /courier/metrics
#   GET  /courier/jobs?status=available|active|delivered&limit=50&offset=0[&respect_offers=true]
#   POST /courier/jobs/{job_id}/accept
#   POST /courier/jobs/{job_id}/start
#   POST /courier/jobs/{job_id}/delivered
#
# Added:
#   POST /courier/offers
#   GET  /courier/offers?status=active|paused|completed|cancelled&limit=50&offset=0
#
# NOTE:
#   For status=active|delivered we now also SELECT assignments.agreed_price_cents
#   and expose it as `agreed_price` (in currency units, e.g. NIS) to the mobile app.
#   We also expose `request_id` (always) and `assignment_id` (for active/delivered)
#   so the app can open a proper "assignment details" screen.

from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Literal, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from decimal import Decimal

from .Database.db import get_db
from .auth_dep import get_current_user

router = APIRouter(prefix="/courier", tags=["courier"])


def _iso(dt):
    """Convert datetime to ISO string (or None)."""
    return dt.isoformat() if dt else None


# ------------------------------ Metrics -------------------------------------

@router.get("/metrics")
def courier_metrics(
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    q_available = text("""
        SELECT COUNT(*) AS c
        FROM requests r
        WHERE r.status = 'open'
          AND r.owner_user_id <> :uid
          AND NOT EXISTS (
            SELECT 1 FROM assignments a
            WHERE a.request_id = r.id
          )
    """)
    available = db.execute(q_available, {"uid": me["id"]}).scalar() or 0

    q_active = text("""
        SELECT COUNT(*) AS c
        FROM assignments a
        JOIN requests r ON r.id = a.request_id
        WHERE a.driver_user_id = :uid
          AND a.status IN ('created','picked_up','in_transit')
    """)
    active = db.execute(q_active, {"uid": me["id"]}).scalar() or 0

    q_delivered = text("""
        SELECT COUNT(*) AS c
        FROM assignments a
        JOIN requests r ON r.id = a.request_id
        WHERE a.driver_user_id = :uid
          AND a.status = 'completed'
    """)
    delivered = db.execute(q_delivered, {"uid": me["id"]}).scalar() or 0

    return {
        "available_count": int(available),
        "active_count": int(active),
        "delivered_count": int(delivered),
    }


# ------------------------------- Jobs List ----------------------------------

@router.get("/jobs")
def courier_jobs(
    status: Literal["available", "active", "delivered"] = Query("available"),
    respect_offers: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    """
    List jobs for the logged-in courier.

    For available:
      - There is no assignment yet.
      - `id` and `request_id` are the same (requests.id).
      - `assignment_id` is null.

    For active/delivered:
      - `id` and `request_id` are the same (requests.id, for backward compatibility
        with /courier/jobs/{job_id}/start|delivered which still expect request_id).
      - `assignment_id` is the real assignments.id (used by the details screen).
      - We also expose `agreed_price` (float), computed from agreed_price_cents.
    """
    if status == "available":
        # Available jobs have no assignment yet → no agreed_price here.
        if respect_offers:
            q = text("""
                SELECT
                  r.id::text AS id,
                  r.id::text AS request_id,
                  NULL::text AS assignment_id,
                  r.type::text AS type,
                  r.status::text AS status,
                  r.from_address,
                  r.to_address,
                  r.window_start,
                  r.window_end,
                  r.notes,
                  r.created_at
                FROM requests r
                WHERE r.status = 'open'
                  AND r.owner_user_id <> :uid
                  AND NOT EXISTS (SELECT 1 FROM assignments a WHERE a.request_id = r.id)
                  AND EXISTS (
                    SELECT 1
                    FROM courier_offers o
                    WHERE o.driver_user_id = :uid
                      AND o.status = 'active'
                      AND r.window_start < o.window_end
                      AND r.window_end > o.window_start
                      AND (o.to_address IS NULL OR o.to_address = r.to_address)
                      AND r.type = ANY (o.types)
                  )
                ORDER BY r.created_at DESC
                LIMIT :limit OFFSET :offset
            """)
        else:
            q = text("""
                SELECT
                  r.id::text AS id,
                  r.id::text AS request_id,
                  NULL::text AS assignment_id,
                  r.type::text AS type,
                  r.status::text AS status,
                  r.from_address,
                  r.to_address,
                  r.window_start,
                  r.window_end,
                  r.notes,
                  r.created_at
                FROM requests r
                WHERE r.status = 'open'
                  AND r.owner_user_id <> :uid
                  AND NOT EXISTS (SELECT 1 FROM assignments a WHERE a.request_id = r.id)
                ORDER BY r.created_at DESC
                LIMIT :limit OFFSET :offset
            """)
        params = {"uid": me["id"], "limit": limit, "offset": offset}

    elif status == "active":
        # Active jobs for this driver. We join assignments to retrieve agreed_price_cents.
        q = text("""
            SELECT
              r.id::text AS id,
              r.id::text AS request_id,
              a.id::text AS assignment_id,
              r.type::text AS type,
              r.status::text AS status,
              r.from_address,
              r.to_address,
              r.window_start,
              r.window_end,
              r.notes,
              r.created_at,
              (a.agreed_price_cents::numeric / 100.0) AS agreed_price
            FROM assignments a
            JOIN requests r ON r.id = a.request_id
            WHERE a.driver_user_id = :uid
              AND a.status IN ('created','picked_up','in_transit')
            ORDER BY a.assigned_at DESC NULLS LAST, r.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        params = {"uid": me["id"], "limit": limit, "offset": offset}

    else:  # delivered
        # Completed jobs for this driver, with final agreed_price.
        q = text("""
            SELECT
              r.id::text AS id,
              r.id::text AS request_id,
              a.id::text AS assignment_id,
              r.type::text AS type,
              r.status::text AS status,
              r.from_address,
              r.to_address,
              r.window_start,
              r.window_end,
              r.notes,
              r.created_at,
              (a.agreed_price_cents::numeric / 100.0) AS agreed_price
            FROM assignments a
            JOIN requests r ON r.id = a.request_id
            WHERE a.driver_user_id = :uid
              AND a.status = 'completed'
            ORDER BY a.completed_at DESC NULLS LAST, r.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        params = {"uid": me["id"], "limit": limit, "offset": offset}

    rows = db.execute(q, params).mappings().all()

    return [
        {
            "id": r["id"],  # kept for backward compatibility (equals request_id)
            "request_id": r.get("request_id"),
            "assignment_id": r.get("assignment_id"),
            "type": r["type"],
            "status": r["status"],
            "from_address": r["from_address"],
            "to_address": r["to_address"],
            "window_start": _iso(r["window_start"]),
            "window_end": _iso(r["window_end"]),
            # New: agreed_price (only for active/delivered; None for available)
            "agreed_price": float(r["agreed_price"])
            if "agreed_price" in r and r["agreed_price"] is not None
            else None,
            "distance_km": None,
            "suggested_pay": None,
            "notes": r["notes"],
            "created_at": _iso(r["created_at"]),
        }
        for r in rows
    ]


# ------------------------------ Job Actions ---------------------------------

@router.post("/jobs/{job_id}/accept")
def courier_accept_job(
    job_id: str,
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    """
    Manual accept of a single open request by a courier.
    This path does NOT set agreed_price_cents (it will remain NULL),
    which is fine for manual, off-PoBA assignments.

    IMPORTANT:
    job_id is still the requests.id (same as request_id/id from /courier/jobs).
    """
    chk = text("""
        SELECT r.id
        FROM requests r
        WHERE r.id = :rid
          AND r.status = 'open'
          AND r.owner_user_id <> :uid
          AND NOT EXISTS (SELECT 1 FROM assignments a WHERE a.request_id = r.id)
        LIMIT 1
    """)
    ok = db.execute(chk, {"rid": job_id, "uid": me["id"]}).first()
    if not ok:
        raise HTTPException(status_code=409, detail="Request not available")

    ins = text("""
        INSERT INTO assignments (
          id, request_id, driver_user_id, assigned_at, status, created_at, updated_at
        ) VALUES (
          gen_random_uuid(), :rid, :uid, NOW(), 'created', NOW(), NOW()
        )
        RETURNING id
    """)
    arow = db.execute(ins, {"rid": job_id, "uid": me["id"]}).mappings().first()

    upd = text("""
        UPDATE requests
        SET status = 'assigned', updated_at = NOW()
        WHERE id = :rid
    """)
    db.execute(upd, {"rid": job_id})

    db.commit()
    return {"ok": True, "job_id": job_id, "assignment_id": arow["id"]}


@router.post("/jobs/{job_id}/start")
def courier_start_job(
    job_id: str,
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    """
    Start a job (mark as in_transit).
    job_id is still the requests.id.
    """
    sel = text("""
        SELECT a.id
        FROM assignments a
        WHERE a.request_id = :rid AND a.driver_user_id = :uid
          AND a.status IN ('created','picked_up','in_transit')
        LIMIT 1
    """)
    a = db.execute(sel, {"rid": job_id, "uid": me["id"]}).first()
    if not a:
        raise HTTPException(status_code=404, detail="Job not found or not yours")

    upd_a = text("""
        UPDATE assignments
        SET status = 'in_transit',
            in_transit_at = COALESCE(in_transit_at, NOW()),
            updated_at = NOW()
        WHERE request_id = :rid AND driver_user_id = :uid
    """)
    db.execute(upd_a, {"rid": job_id, "uid": me["id"]})

    upd_r = text("""
        UPDATE requests
        SET status = 'in_transit', updated_at = NOW()
        WHERE id = :rid
    """)
    db.execute(upd_r, {"rid": job_id})

    db.commit()
    return {"ok": True, "job_id": job_id}


@router.post("/jobs/{job_id}/delivered")
def courier_delivered_job(
    job_id: str,
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    """
    Mark job as delivered/completed.
    job_id is still the requests.id.
    """
    sel = text("""
        SELECT a.id
        FROM assignments a
        WHERE a.request_id = :rid AND a.driver_user_id = :uid
          AND a.status IN ('created','picked_up','in_transit')
        LIMIT 1
    """)
    a = db.execute(sel, {"rid": job_id, "uid": me["id"]}).first()
    if not a:
        raise HTTPException(status_code=404, detail="Job not found or not yours")

    upd_a = text("""
        UPDATE assignments
        SET status = 'completed',
            completed_at = NOW(),
            updated_at = NOW()
        WHERE request_id = :rid AND driver_user_id = :uid
    """)
    db.execute(upd_a, {"rid": job_id, "uid": me["id"]})

    upd_r = text("""
        UPDATE requests
        SET status = 'completed', updated_at = NOW()
        WHERE id = :rid
    """)
    db.execute(upd_r, {"rid": job_id})

    db.commit()
    return {"ok": True, "job_id": job_id}


# --------------------------- Courier Offers (NEW) ---------------------------

class OfferCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_address: str = Field(..., min_length=3, max_length=255)
    to_address: Optional[str] = Field(None, max_length=255)  # None = any destination
    window_start: datetime
    window_end: datetime
    min_price: Decimal = Field(..., gt=0)
    types: List[str] = Field(default_factory=lambda: ["package"])  # ['package','passenger']
    notes: Optional[str] = None

    @field_validator("window_end")
    @classmethod
    def _win_ok(cls, v, info):
        s = info.data.get("window_start")
        if s and v <= s:
            raise ValueError("window_end must be after window_start")
        return v


@router.post("/offers", status_code=201)
def create_courier_offer(
    payload: OfferCreate,
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    """
    Create a courier offer row.
    """
    sql = text("""
        INSERT INTO courier_offers (
          driver_user_id,
          from_address, to_address,
          window_start, window_end,
          min_price, types, notes, status
        ) VALUES (
          :uid,
          :from_address, :to_address,
          :window_start, :window_end,
          :min_price, :types, :notes, 'active'
        )
        RETURNING id::text AS id, status::text AS status, created_at
    """)
    row = db.execute(sql, {
        "uid": me["id"],
        "from_address": payload.from_address,
        "to_address": payload.to_address,
        "window_start": payload.window_start,
        "window_end": payload.window_end,
        "min_price": str(payload.min_price),
        "types": payload.types,
        "notes": payload.notes,
    }).mappings().first()
    db.commit()
    return {"id": row["id"], "status": row["status"], "created_at": _iso(row["created_at"])}


@router.get("/offers")
def list_my_offers(
    status: Optional[str] = Query(None),  # active | paused | completed | cancelled
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    """
    List offers for the logged-in courier.
    """
    base = """
        SELECT
          id::text AS id,
          driver_user_id::text AS driver_user_id,
          from_address, to_address,
          window_start, window_end,
          min_price::text AS min_price,
          types, notes, status,
          created_at, updated_at
        FROM courier_offers
        WHERE driver_user_id = :uid
    """
    if status:
        base += " AND status = :status"
    base += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

    params = {"uid": me["id"], "limit": limit, "offset": offset}
    if status:
        params["status"] = status

    rows = db.execute(text(base), params).mappings().all()
    return [
        {
            "id": r["id"],
            "from_address": r["from_address"],
            "to_address": r["to_address"],
            "window_start": _iso(r["window_start"]),
            "window_end": _iso(r["window_end"]),
            "min_price": r["min_price"],
            "types": r["types"],
            "notes": r["notes"],
            "status": r["status"],
            "created_at": _iso(r["created_at"]),
            "updated_at": _iso(r["updated_at"]),
        }
        for r in rows
    ]
