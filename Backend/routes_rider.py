# routes_rider.py
# Rider dashboard API + create: requests of type 'passenger' (נרמול מ-ride) עבור המשתמש המחובר.

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from decimal import Decimal

from .Database.db import get_db
from .auth_dep import get_current_user  # returns dict with 'id'
from .services.geocoding import geocode_address  # ⬅ חדש: גאוקוד בצד שרת

router = APIRouter(prefix="/rider", tags=["rider"])

# כולל גם legacy 'ride' להצגה במסכים (קריאה/רשימות), אבל CREATE ינרמל ל-passenger
RIDER_TYPES: List[str] = ["passenger", "ride"]

def _status_bucket_to_sql_list(bucket: str) -> List[str]:
    b = (bucket or "").lower()
    if b == "open":
        return ["open"]
    if b == "active":
        return ["assigned", "in_transit"]
    if b in ("completed", "delivered"):
        return ["completed"]
    raise HTTPException(status_code=400, detail="Invalid status bucket")

def _uid(me: Dict[str, Any]) -> str:
    if not me or not me.get("id"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(me["id"])

# ------------------------------- KPIs -------------------------------

@router.get("/metrics")
def rider_metrics(
    db: Session = Depends(get_db),
    me: Dict[str, Any] = Depends(get_current_user),
):
    uid = _uid(me)
    type_cast_list = ", ".join([f"CAST(:t{i} AS request_type)" for i in range(len(RIDER_TYPES))])
    type_params = {f"t{i}": t for i, t in enumerate(RIDER_TYPES)}

    rows = db.execute(
        text(f"""
            SELECT status::text AS status, COUNT(*) AS cnt
            FROM requests
            WHERE owner_user_id = :uid
              AND type IN ({type_cast_list})
            GROUP BY status
        """),
        {"uid": uid, **type_params},
    ).mappings().all()

    by = {r["status"]: int(r["cnt"]) for r in rows}
    return {
        "open_count": by.get("open", 0),
        "active_count": by.get("assigned", 0) + by.get("in_transit", 0),
        "completed_count": by.get("completed", 0),
        "cancelled_count": by.get("cancelled", 0),
    }

# ------------------------------ List ------------------------------

@router.get("/requests")
def list_rider_requests(
    status: str = Query("open", description="open | active | completed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    me: Dict[str, Any] = Depends(get_current_user),
):
    uid = _uid(me)
    statuses = _status_bucket_to_sql_list(status)

    status_cast_list = ", ".join([f"CAST(:s{i} AS request_status)" for i in range(len(statuses))])
    type_cast_list   = ", ".join([f"CAST(:t{i} AS request_type)" for i in range(len(RIDER_TYPES))])

    params = {
        "uid": uid,
        "limit": limit,
        "offset": offset,
        **{f"s{i}": s for i, s in enumerate(statuses)},
        **{f"t{i}": t for i, t in enumerate(RIDER_TYPES)},
    }

    rows = db.execute(
        text(f"""
            SELECT
              id::text                                AS id,
              owner_user_id::text                     AS owner_user_id,
              type::text                              AS type,
              from_address,
              to_address,
              window_start,
              window_end,
              passengers,
              notes,
              max_price::numeric                      AS max_price,
              status::text                            AS status,
              created_at,
              updated_at
            FROM requests
            WHERE owner_user_id = :uid
              AND type IN ({type_cast_list})
              AND status IN ({status_cast_list})
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).mappings().all()

    def _iso(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "status": r["status"],
            "from_address": r["from_address"],
            "to_address": r["to_address"],
            "window_start": _iso(r["window_start"]),
            "window_end": _iso(r["window_end"]),
            "passengers": r["passengers"],
            "notes": r["notes"],
            "max_price": float(r["max_price"]) if r["max_price"] is not None else None,
            "created_at": _iso(r["created_at"]),
        })
    return out

# --------------------------- CREATE (normalized to passenger + geocode) ---------------------------

class RiderRequestCreate(BaseModel):
    from_address: str
    to_address: str
    window_start: datetime
    window_end: datetime
    passengers: int = Field(ge=1)
    notes: str | None = None
    max_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)

    # אופציונלי: אם הפרונט יספק lat/lon נשמור אותם ונחסוך גאוקוד
    from_lat: Optional[float] = None
    from_lon: Optional[float] = None
    to_lat:   Optional[float] = None
    to_lon:   Optional[float] = None

    @field_validator("window_end")
    @classmethod
    def _validate_window(cls, v, info):
        start = info.data.get("window_start")
        if start and v <= start:
            raise ValueError("window_end must be after window_start")
        return v

@router.post("/requests")
def create_rider_request(
    payload: RiderRequestCreate,
    db: Session = Depends(get_db),
    me: Dict[str, Any] = Depends(get_current_user),
):
    uid = _uid(me)

    # 1) נרמול סוג: תמיד passenger (גם אם המסך חושב "ride")
    norm_type = "passenger"

    # 2) גאוקוד אם חסר lat/lon
    from_lat, from_lon = payload.from_lat, payload.from_lon
    to_lat,   to_lon   = payload.to_lat,   payload.to_lon

    if from_lat is None or from_lon is None:
        src = geocode_address(payload.from_address)
        if src is None:
            raise HTTPException(400, detail="לא מצאנו את כתובת המוצא. נסו לכתוב: רחוב ומספר, עיר (לדוגמה: הרצל 10, חולון)")
        from_lat, from_lon = src

    if to_lat is None or to_lon is None:
        dst = geocode_address(payload.to_address)
        if dst is None:
            raise HTTPException(400, detail="לא מצאנו את כתובת היעד. נסו לכתוב: רחוב ומספר, עיר (לדוגמה: הרצל 10, חולון)")
        to_lat, to_lon = dst

    # 3) הוספה עם קואורדינטות (כדי שה-matcher יראה את הבקשה)
    row = db.execute(
        text("""
            INSERT INTO requests (
              owner_user_id,
              type,
              status,
              from_address, from_lat, from_lon,
              to_address,   to_lat,   to_lon,
              window_start, window_end,
              passengers,
              notes,
              max_price,
              created_at, updated_at
            ) VALUES (
              :uid,
              CAST(:type AS request_type),
              CAST(:status AS request_status),
              :from_address, :from_lat, :from_lon,
              :to_address,   :to_lat,   :to_lon,
              :window_start, :window_end,
              :passengers,
              :notes,
              :max_price,
              NOW(), NOW()
            )
            RETURNING
              id::text                     AS id,
              owner_user_id::text          AS owner_user_id,
              type::text                   AS type,
              status::text                 AS status,
              from_address, to_address,
              window_start, window_end,
              passengers, notes, max_price::numeric,
              created_at, updated_at
        """),
        {
          "uid": uid,
          "type": norm_type,         # 👈 תמיד passenger
          "status": "open",
          "from_address": payload.from_address,
          "from_lat": from_lat,
          "from_lon": from_lon,
          "to_address": payload.to_address,
          "to_lat": to_lat,
          "to_lon": to_lon,
          "window_start": payload.window_start,
          "window_end": payload.window_end,
          "passengers": payload.passengers,
          "notes": payload.notes,
          "max_price": str(payload.max_price) if payload.max_price is not None else None,
        },
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=500, detail="failed_to_create_ride_request")

    db.commit()

    def _iso(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    return {
        "id": row["id"],
        "owner_user_id": row["owner_user_id"],
        "type": row["type"],      # יהיה 'passenger'
        "status": row["status"],
        "from_address": row["from_address"],
        "to_address": row["to_address"],
        "window_start": _iso(row["window_start"]),
        "window_end": _iso(row["window_end"]),
        "passengers": row["passengers"],
        "notes": row["notes"],
        "max_price": float(row["max_price"]) if row["max_price"] is not None else None,
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }
