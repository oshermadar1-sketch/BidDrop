# app/auction/routes_auction.py
# Clearing via IDA* using courier_offers (supply).
# Sends push notifications on matches, BUT only if now >= requests.push_defer_until (client-side defer).

from __future__ import annotations
from fastapi import APIRouter, Depends
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, text
from sqlalchemy.exc import OperationalError
from datetime import datetime, timezone
import logging, json, time

# get_db – compatible with different project layouts
try:
    from .Database.db import get_db
    from .models import Users, Requests, Assignments, CourierOffers
except Exception:
    from Backend.Database.db import get_db  # type: ignore
    from Backend.models import Users, Requests, Assignments, CourierOffers  # type: ignore

# IDA* clearing engine
try:
    from .auction.clearing_engine import Ask, DriverState, Point, Weights, solve_clearing_ida
except Exception:
    from app.auction.clearing_engine import Ask, DriverState, Point, Weights, solve_clearing_ida  # type: ignore

# Push service
try:
    from .services.push import send_expo_async, fire_and_forget
except Exception:
    from Backend.services.push import send_expo_async, fire_and_forget  # type: ignore

router = APIRouter(prefix="/auction", tags=["auction"])

# Logger for structured “match” lines (configured in Backend/main.py)
match_logger = logging.getLogger("match")


# ------------------------- Push defer helpers -------------------------

def _should_send_push_request(db: Session, request_id: str) -> bool:
    row = db.execute(
        text("SELECT push_defer_until FROM requests WHERE id = :rid"),
        {"rid": request_id},
    ).mappings().first()
    if not row:
        return True
    ts = row.get("push_defer_until")
    if ts is None:
        return True
    return datetime.now(timezone.utc) >= ts


def _should_send_push_driver(db: Session, driver_user_id: str) -> bool:
    row = db.execute(
        text("""
            SELECT MAX(push_defer_until) AS latest_defer
            FROM courier_offers
            WHERE driver_user_id = :uid AND status = 'active'
        """),
        {"uid": driver_user_id},
    ).mappings().first()
    if not row:
        return True
    ts = row.get("latest_defer")
    if ts is None:
        return True
    return datetime.now(timezone.utc) >= ts


# ------------------------- Type normalization -------------------------

def _norm_req_type(t: str) -> str:
    """
    Normalize request.type:
    - 'ride' and 'passenger' → 'passenger'
    - 'package' → 'package'
    """
    t = (t or "").strip().lower()
    if t in ("ride", "passenger"):
        return "passenger"
    return "package"


def _type_matches(req_t: str, offer_types: list[str] | None) -> bool:
    """
    Offer stores ARRAY(TEXT), e.g. ['package'] or ['package','passenger'].
    We compare lowercase and allow ride≈passenger.
    """
    if not offer_types:
        return False
    norm = [x.strip().lower() for x in offer_types]
    if req_t == "passenger":
        return ("passenger" in norm) or ("ride" in norm)
    if req_t == "package":
        return "package" in norm
    return False


# ------------------------- Time overlap with tolerance -------------------------

_TOL_MIN = 20  # minutes tolerance

def _minutes(ts: datetime | None) -> float | None:
    return None if ts is None else ts.timestamp() / 60.0

def _windows_overlap(req_start_min, req_end_min, off_start_min, off_end_min) -> bool:
    if req_start_min is None or req_end_min is None:
        return True
    tol = _TOL_MIN
    return (off_start_min <= (req_end_min + tol)) and (off_end_min + tol >= req_start_min)


# ------------------------- Main clearing -------------------------

def run_clearing_tick(
    db: Session,
    avg_kmh: float = 40.0,
    w_dist: float = 1.0,
    w_eta: float = 0.2,
    w_price: float = 1.0,
    w_rating_penalty: float = 0.3,
    mark_offer_assigned: bool = True,
):
    # 1) Load open requests with coordinates
    req_rows: List[Requests] = (
        db.query(Requests)
        .filter(
            and_(
                Requests.status == "open",
                Requests.from_lat.isnot(None),
                Requests.from_lon.isnot(None),
                Requests.to_lat.isnot(None),
                Requests.to_lon.isnot(None),
            )
        )
        .order_by(Requests.created_at.asc())
        .all()
    )
    if not req_rows:
        return {"cleared": False, "reason": "no open requests with coordinates"}

    # Map to Ask DTOs
    asks: List[Ask] = []
    for r in req_rows:
        asks.append(
            Ask(
                id=str(r.id),
                pickup=Point(float(r.from_lat), float(r.from_lon)),
                dropoff=Point(float(r.to_lat), float(r.to_lon)),
                size=float((r.passengers or 1)),
                max_price=float(r.max_price or 0),
                window_start=_minutes(r.window_start),
                window_end=_minutes(r.window_end),
            )
        )

    # 2) Load active courier offers
    offer_rows: List[CourierOffers] = (
        db.query(CourierOffers)
        .filter(CourierOffers.status == "active")
        .order_by(CourierOffers.created_at.asc())
        .all()
    )
    if not offer_rows:
        return {"cleared": False, "reason": "no active courier offers"}

    # 3) Load driver users for those offers
    driver_ids = sorted({o.driver_user_id for o in offer_rows})
    drivers_rows: List[Users] = (
        db.query(Users)
        .filter(and_(Users.id.in_(driver_ids), Users.role == "driver"))
        .all()
    )
    if not drivers_rows:
        return {"cleared": False, "reason": "no valid drivers for offers"}

    # Driver anchor: use first request pickup (no live driver GPS)
    anchor_point = Point(float(req_rows[0].from_lat), float(req_rows[0].from_lon))

    # Build driver states (capacity=1 for MVP)
    drivers: List[DriverState] = []
    driver_index_by_id: Dict[str, int] = {}
    for j, u in enumerate(drivers_rows):
        drivers.append(
            DriverState(
                driver_id=str(u.id),
                pos=anchor_point,
                time_min=0.0,
                capacity_left=1.0,
                rating=float(u.rating or 0.0),
            )
        )
        driver_index_by_id[str(u.id)] = j

    # Group offers by driver
    offers_by_driver: Dict[str, List[CourierOffers]] = {}
    for off in offer_rows:
        offers_by_driver.setdefault(str(off.driver_user_id), []).append(off)

    # Debug counters (help understand why there are no matches)
    dbg_counts = {
        "total_pairs_checked": 0,
        "filtered_by_type": 0,
        "filtered_by_time": 0,
        "filtered_by_price": 0,
    }

    allowed_drivers_per_ask: List[List[int]] = [[] for _ in asks]
    price_per_pair: Dict[Tuple[int, int], float] = {}
    price_lb_per_ask: List[float] = [float("inf")] * len(asks)

    for req_idx, r in enumerate(req_rows):
        req_type = _norm_req_type(str(r.type))
        req_ws = asks[req_idx].window_start
        req_we = asks[req_idx].window_end

        for drv_user_id, drv_idx in driver_index_by_id.items():
            best_for_driver: float | None = None

            for off in offers_by_driver.get(drv_user_id, []):
                dbg_counts["total_pairs_checked"] += 1

                off_ws = _minutes(off.window_start)
                off_we = _minutes(off.window_end)

                # type
                if not _type_matches(req_type, off.types):
                    dbg_counts["filtered_by_type"] += 1
                    continue

                # time
                if not _windows_overlap(req_ws, req_we, off_ws, off_we):
                    dbg_counts["filtered_by_time"] += 1
                    continue

                # price: if request has no cap (None/0) → do not filter
                req_cap = None
                try:
                    req_cap = float(r.max_price) if r.max_price is not None else None
                except Exception:
                    req_cap = None
                if req_cap is not None and req_cap <= 0:
                    req_cap = None

                off_min = None
                try:
                    off_min = float(off.min_price) if off.min_price is not None else None
                except Exception:
                    off_min = None

                if req_cap is not None and off_min is not None and off_min > req_cap:
                    dbg_counts["filtered_by_price"] += 1
                    continue

                # feasible
                if off_min is not None:
                    if best_for_driver is None or off_min < best_for_driver:
                        best_for_driver = off_min

            if best_for_driver is not None:
                allowed_drivers_per_ask[req_idx].append(drv_idx)
                price_per_pair[(req_idx, drv_idx)] = best_for_driver
                if best_for_driver < price_lb_per_ask[req_idx]:
                    price_lb_per_ask[req_idx] = best_for_driver

    # prune asks with no candidates
    keep_mask = [len(allowed_drivers_per_ask[i]) > 0 for i in range(len(asks))]
    if not any(keep_mask):
        return {
            "cleared": False,
            "reason": "no feasible ask-offer pairs (type/time/budget filters)",
            "debug_counts": dbg_counts,
            "sample": {
                "open_requests": len(req_rows),
                "active_offers": len(offer_rows),
            },
        }

    old_to_new: Dict[int, int] = {}
    asks_pruned: List[Ask] = []
    allowed_pruned: List[List[int]] = []
    price_lb_pruned: List[float] = []
    for i, keep in enumerate(keep_mask):
        if keep:
            new_i = len(asks_pruned)
            old_to_new[i] = new_i
            asks_pruned.append(asks[i])
            allowed_pruned.append(allowed_drivers_per_ask[i])
            price_lb_pruned.append(price_lb_per_ask[i])

    price_per_pair_pruned: Dict[Tuple[int, int], float] = {}
    for (old_i, j), p in price_per_pair.items():
        if old_i in old_to_new:
            price_per_pair_pruned[(old_to_new[old_i], j)] = p

    # K bound = number of drivers
    max_assign = len(drivers_rows)
    if len(asks_pruned) > max_assign and max_assign > 0:
        sel = sorted(
            range(len(asks_pruned)),
            key=lambda i: (price_lb_pruned[i], asks_pruned[i].window_start or 0)
        )[:max_assign]

        def _take(lst):
            return [lst[i] for i in sel]

        asks_pruned     = _take(asks_pruned)
        allowed_pruned  = _take(allowed_pruned)
        price_lb_pruned = _take(price_lb_pruned)

        idx_map = {old_i: new_i for new_i, old_i in enumerate(sel)}
        price_per_pair_pruned = {
            (idx_map[i], j): p
            for (i, j), p in price_per_pair_pruned.items()
            if i in idx_map
        }

    weights = Weights(
        w_dist=w_dist,
        w_eta=w_eta,
        w_price=w_price,
        w_rating_penalty=w_rating_penalty,
    )

    plan, total_penalty, dbg = solve_clearing_ida(
        asks=asks_pruned,
        initial_drivers=drivers,
        avg_kmh=avg_kmh,
        weights=weights,
        rating_max=5.0,
        allowed_drivers_per_ask=allowed_pruned,
        bid_amounts=price_per_pair_pruned,  # here "bid" == offer.min_price
        price_lb_per_ask=price_lb_pruned,
    )
    if not plan:
        return {"cleared": False, "reason": "no optimal plan found", "debug": dbg, "debug_counts": dbg_counts}

    # ---------------------------------------------------------------------
    # Persist (deadlock-safe):
    #  - Lock the request row first (FOR UPDATE SKIP LOCKED) in a CTE
    #  - Insert into assignments only if we successfully locked an OPEN request
    #  - Update request status to 'assigned' in the same statement
    #  - Retry on deadlocks a few times with small backoff
    # ---------------------------------------------------------------------
    pruned_to_row = {new_i: req_rows[old_i] for old_i, new_i in old_to_new.items()}
    row_by_id: Dict[str, Requests] = {str(r.id): r for r in req_rows}
    results = []
    assigned_ts = datetime.now(timezone.utc)

    # Single statement that locks -> inserts -> updates, avoiding cross-locks
    claim_sql = text("""
        WITH locked AS (
            SELECT id
            FROM requests
            WHERE id = :rid AND status = 'open'
            FOR UPDATE SKIP LOCKED
        ), ins AS (
            INSERT INTO assignments (request_id, driver_user_id, assigned_at, status)
            SELECT :rid, :uid, :ts, CAST(:st AS assignment_status)
            FROM locked
            ON CONFLICT (request_id) DO NOTHING
            RETURNING request_id
        )
        UPDATE requests r
        SET status = 'assigned'
        FROM ins
        WHERE r.id = ins.request_id
        RETURNING r.id::text AS request_id
    """)

    def _try_claim_once(rid: str, uid: str) -> bool:
        row = db.execute(
            claim_sql,
            {"rid": rid, "uid": uid, "ts": assigned_ts, "st": "created"},
        ).mappings().first()
        return bool(row and row.get("request_id"))

    for (new_i, drv_j) in plan:
        rid = str(pruned_to_row[new_i].id)
        uid = str(drivers_rows[drv_j].id)

        # Small retry loop for deadlocks/transient errors
        claimed = False
        for attempt in range(3):
            try:
                if _try_claim_once(rid, uid):
                    claimed = True
                break
            except OperationalError as e:
                if "deadlock detected" in str(e).lower() and attempt < 2:
                    # brief sleep then retry
                    time.sleep(0.05 * (attempt + 1))
                    continue
                raise

        if not claimed:
            # Someone else claimed/assigned it (or we skipped due to lock) → skip
            continue

        # Optionally mark the cheapest consistent offer as assigned
        if mark_offer_assigned:
            req_row = pruned_to_row[new_i]
            m_offers = [
                off
                for off in offers_by_driver.get(uid, [])
                if _type_matches(_norm_req_type(str(req_row.type)), off.types)
                and (
                    req_row.window_start is None
                    or req_row.window_end is None
                    or (
                        off.window_start is not None
                        and off.window_end is not None
                        and off.window_start <= req_row.window_end
                        and off.window_end >= req_row.window_start
                    )
                )
                and (
                    req_row.max_price is None
                    or off.min_price is None
                    or float(off.min_price) <= float(req_row.max_price)
                )
            ]
            if m_offers:
                m_offers.sort(key=lambda o: float(o.min_price or 0))
                m_offers[0].status = "assigned"

        results.append({"request_id": rid, "driver_user_id": uid})

    db.commit()

    # ---- Structured logs per match (owner name + addresses) ----
    for m in results:
        try:
            req_row = row_by_id.get(m["request_id"])
            owner_name = None
            owner_user_id = None
            if req_row and req_row.owner_user_id:
                owner_user_id = str(req_row.owner_user_id)
                owner_row = (
                    db.query(Users)
                    .filter(Users.id == req_row.owner_user_id)
                    .first()
                )
                if owner_row:
                    first = getattr(owner_row, "first_name", "") or ""
                    last = getattr(owner_row, "last_name", "") or ""
                    owner_name = f"{first} {last}".strip() or None

            match_logger.info(json.dumps({
                "event": "match_found",
                "request_id": m["request_id"],
                "driver_user_id": m["driver_user_id"],
                "owner_user_id": owner_user_id,
                "owner_name": owner_name,
                "request_type": getattr(req_row, "type", None) if req_row else None,
                "from_address": getattr(req_row, "from_address", None) if req_row else None,
                "to_address": getattr(req_row, "to_address", None) if req_row else None,
                "ts": int(datetime.now(timezone.utc).timestamp()),
                "objective": total_penalty,
                "debug": dbg,
            }, ensure_ascii=False))
        except Exception:
            # Don't break clearing on logging issues
            pass

    # Push notifications (owner + driver) — only if defer window passed
    for m in results:
        req_id = m["request_id"]
        drv_id = m["driver_user_id"]

        send_now_owner = _should_send_push_request(db, req_id)
        send_now_driver = _should_send_push_driver(db, drv_id)

        owner_row = db.execute(
            text("SELECT owner_user_id FROM requests WHERE id = :rid"),
            {"rid": req_id},
        ).fetchone()
        owner_id = str(owner_row[0]) if owner_row else None

        ids_list = list({x for x in [owner_id, drv_id] if x})
        tokens = {}
        if ids_list:
            rows = db.execute(
                text("SELECT id::text, expo_push_token FROM users WHERE id::text = ANY(:ids)"),
                {"ids": ids_list},
            ).mappings().all()
            tokens = {r["id"]: r["expo_push_token"] for r in rows if r["expo_push_token"]}

        print(f"[AUCTION] tokens={tokens}  send_owner={send_now_owner}  send_driver={send_now_driver}")

        if send_now_owner and owner_id and owner_id in tokens:
            fire_and_forget(
                send_expo_async(
                    tokens[owner_id],
                    "נמצאה לך התאמה 🚗",
                    "יש נהג שמתאים לבקשה שלך. פתחי את האפליקציה לאישור.",
                    {"screen": "Assignment", "request_id": req_id},
                    sound="default",
                    channel_id="default",
                )
            )

        if send_now_driver and drv_id in tokens:
            fire_and_forget(
                send_expo_async(
                    tokens[drv_id],
                    "התאמה חדשה עבורך ✅",
                    "יש נסיעה שמתאימה להצעה שלך. פתח כדי לקבל/לדחות.",
                    {"screen": "Assignment", "request_id": req_id, "driver_user_id": drv_id},
                    sound="default",
                    channel_id="default",
                )
            )
        else:
            # Defer window still active → don't push. (The waiting screen will show the match live.)
            pass

    return {
        "cleared": True,
        "matches": results,
        "objective": {"total_weighted_penalty": total_penalty},
        "debug": dbg,
        "debug_counts": dbg_counts,
    }


@router.post("/clear")
def clear_market_endpoint(
    avg_kmh: float = 40.0,
    w_dist: float = 1.0,
    w_eta: float = 0.2,
    w_price: float = 1.0,
    w_rating_penalty: float = 0.3,
    mark_offer_assigned: bool = True,
    db: Session = Depends(get_db),
):
    return run_clearing_tick(
        db=db,
        avg_kmh=avg_kmh,
        w_dist=w_dist,
        w_eta=w_eta,
        w_price=w_price,
        w_rating_penalty=w_rating_penalty,
        mark_offer_assigned=mark_offer_assigned,
    )
