from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks

# NOTE: We *try* to import the auto-matcher trigger. If it's not available yet,
# we fall back to a no-op so the service won't crash.
try:
    from .matching_auto import try_auto_match  # preferred location
except Exception:
    try:
        from Backend.matching_auto import try_auto_match  # alternative layout
    except Exception:
        def try_auto_match() -> None:
            """No-op fallback when auto-matching module isn't present."""
            return

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Literal, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# db session
from .Database.db import get_db

# current user dep
from .auth_dep import get_current_user

# server-side geocoding
from .services.geocoding import geocode_address

from sqlalchemy import text

router = APIRouter(prefix="", tags=["requests"])

# ---------- Pydantic v2 input model ----------
class RequestCreate(BaseModel):
  model_config = ConfigDict(from_attributes=True)

  # Include 'ride' so the frontend can send ride directly
  type: Literal["package", "passenger", "ride"] = "package"
  from_address: str = Field(..., min_length=3, max_length=255)
  to_address: str = Field(..., min_length=3, max_length=255)
  window_start: datetime
  window_end: datetime

  notes: Optional[str] = None
  max_price: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
  pickup_contact_name: Optional[str] = Field(None, max_length=100)
  pickup_contact_phone: Optional[str] = Field(None, max_length=32)

  # Optional client-provided coords; server will fill if missing
  from_lat: Optional[float] = None
  from_lon: Optional[float] = None
  to_lat: Optional[float] = None
  to_lon: Optional[float] = None
  passengers: Optional[int] = None

  @field_validator("window_end")
  @classmethod
  def _validate_window(cls, v, info):
    start = info.data.get("window_start")
    if start and v <= start:
      raise ValueError("window_end must be after window_start")
    return v

# ---------- Helper ----------
def _user_id(u) -> str:
  """
  Supports both dict and object user representations.
  Returns user id or None.
  """
  if hasattr(u, "id"):
    return getattr(u, "id")
  if isinstance(u, dict):
    return u.get("id") or u.get("user_id")
  return None

# ---------- Routes ----------
@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_request(
  payload: RequestCreate,
  db = Depends(get_db),
  current_user = Depends(get_current_user),
  background_tasks: BackgroundTasks = None,
):
  """
  Create a user request. After successful insert+commit we trigger a debounced
  auto-matching pipeline (non-blocking). The trigger is safe to call even if
  auto-matching is disabled by env; it'll no-op.
  """
  uid = _user_id(current_user)
  if not uid:
    raise HTTPException(status_code=401, detail="Unauthorized (no user id)")

  # If coords missing -> geocode on server
  from_lat = payload.from_lat
  from_lon = payload.from_lon
  to_lat = payload.to_lat
  to_lon = payload.to_lon

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

  # Normalize type: 'ride' → treat as 'passenger' for matching logic
  raw_type = str(payload.type)
  norm_type = "passenger" if raw_type.strip().lower() == "ride" else raw_type

  params = {
    "owner_user_id": uid,
    "type": norm_type,  # normalized for downstream logic
    "from_address": payload.from_address,
    "from_lat": from_lat,
    "from_lon": from_lon,
    "to_address": payload.to_address,
    "to_lat": to_lat,
    "to_lon": to_lon,
    "passengers": payload.passengers,
    "notes": payload.notes,
    "window_start": payload.window_start,
    "window_end": payload.window_end,
    "status": "open",
    "max_price": str(payload.max_price),  # psycopg-friendly
    "pickup_contact_name": payload.pickup_contact_name,
    "pickup_contact_phone": payload.pickup_contact_phone,
  }

  sql = text(
    """
    INSERT INTO requests (
      owner_user_id, type,
      from_address, from_lat, from_lon,
      to_address, to_lat, to_lon,
      passengers, notes,
      window_start, window_end, status,
      max_price, pickup_contact_name, pickup_contact_phone
    ) VALUES (
      :owner_user_id, :type,
      :from_address, :from_lat, :from_lon,
      :to_address, :to_lat, :to_lon,
      :passengers, :notes,
      :window_start, :window_end, :status,
      :max_price, :pickup_contact_name, :pickup_contact_phone
    )
    RETURNING id, status, created_at
    """
  )

  try:
    if hasattr(db, "execute"):
      result = db.execute(sql, params)
      row = result.mappings().first()
      if hasattr(db, "commit"):
        db.commit()
    else:
      res = await db.execute(sql, params)
      row = res.mappings().first()
      await db.commit()
  except Exception as e:
    print("[/requests] insert error:", repr(e))
    raise HTTPException(status_code=400, detail=str(e))

  if not row:
    raise HTTPException(status_code=500, detail="Insert failed (no row)")

  # Non-blocking, debounced auto-match trigger (safe if module/env disabled)
  if background_tasks is not None:
    background_tasks.add_task(try_auto_match)

  return {
    "id": str(row["id"]),
    "status": row["status"],
    "created_at": row["created_at"],
  }

# ---------- Defer push for this request ----------
@router.post("/requests/{request_id}/defer_push")
async def defer_push_for_request(
  request_id: str,
  seconds: int = Query(60, ge=0, le=600),
  db = Depends(get_db),
  current_user = Depends(get_current_user),
):
  """
  TEMPORARILY DISABLED:
  We keep this endpoint for compatibility with the app,
  but it does NOT update requests.push_defer_until anymore.
  This avoids hiding the request from /poba/requests-open during PoBA debugging.
  """
  uid = _user_id(current_user)
  if not uid:
    raise HTTPException(status_code=401, detail="Unauthorized")

  # verify ownership (still enforced)
  sel = text("SELECT owner_user_id FROM requests WHERE id = :rid")
  try:
    if hasattr(db, "execute"):
      owner_row = db.execute(sel, {"rid": request_id}).mappings().first()
    else:
      res = await db.execute(sel, {"rid": request_id})
      owner_row = res.mappings().first()
  except Exception as e:
    print("[/requests/defer_push] select error:", repr(e))
    raise HTTPException(400, detail="failed to load request")

  if not owner_row:
    raise HTTPException(404, detail="request not found")
  if str(owner_row["owner_user_id"]) != str(uid):
    raise HTTPException(403, detail="not your request")

  # IMPORTANT: no DB update to push_defer_until here.
  # We just return a dummy timestamp indicating "no real defer".
  defer_until = datetime.now(timezone.utc)

  return {
    "ok": True,
    "push_defer_until": defer_until.isoformat(),
    "note": "defer_push temporarily disabled for PoBA debug; no DB change performed",
  }

# ---------- Match status for waiting screen ----------
@router.get("/requests/{request_id}/match_status")
async def get_match_status(
  request_id: str,
  db = Depends(get_db),
  current_user = Depends(get_current_user),
):
  """
  Returns a simple status for a request (only to the owner):
  - {"status": "matched", "assignment_id": "...", "driver_user_id": "..."}
  - {"status": "pending"}   (request exists, no assignment yet)
  - {"status": "none"}      (no access / not found)
  """
  uid = _user_id(current_user)
  if not uid:
    return {"status": "none"}

  # verify ownership
  sel = text("SELECT owner_user_id::text, status FROM requests WHERE id = :rid")
  try:
    if hasattr(db, "execute"):
      req = db.execute(sel, {"rid": request_id}).mappings().first()
    else:
      res = await db.execute(sel, {"rid": request_id})
      req = res.mappings().first()
  except Exception as e:
    print("[/requests/match_status] select error:", repr(e))
    return {"status": "none"}

  if not req:
    return {"status": "none"}
  if str(req["owner_user_id"]) != str(uid):
    return {"status": "none"}

  # if already assigned → return latest assignment info
  if str(req["status"]) == "assigned":
    q_asg = text(
      """
      SELECT id AS assignment_id, driver_user_id::text
      FROM assignments
      WHERE request_id = :rid
      ORDER BY assigned_at DESC
      LIMIT 1
      """
    )
    try:
      if hasattr(db, "execute"):
        asg = db.execute(q_asg, {"rid": request_id}).mappings().first()
      else:
        res = await db.execute(q_asg, {"rid": request_id})
        asg = res.mappings().first()
    except Exception as e:
      print("[/requests/match_status] asg select error:", repr(e))
      return {"status": "pending"}

    payload = {"status": "matched"}
    if asg:
      payload["assignment_id"] = str(asg["assignment_id"])
      payload["driver_user_id"] = str(asg["driver_user_id"])
    return payload

  return {"status": "pending"}

@router.get("/healthz")
def healthz():
  return {"ok": True}
