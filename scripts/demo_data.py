"""
DEMO DATA for showing the trust score in the app. NOT real data.

Every demo row is marked: users have wallet_address 'DEMO-...' and a first name starting
with '[דמו]', demo requests/offers have '[דמו]' in their address/notes.

Run from the project root, while the backend server is running (python = .venv python):
    python scripts/demo_data.py add       # 3 demo couriers with demo history + active offers
    python scripts/demo_data.py status    # show the demo couriers and their trust scores
    python scripts/demo_data.py complete  # demo courier finishes your latest matched delivery
    python scripts/demo_data.py remove    # delete every demo row
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import requests  # noqa: E402

from Backend.Database.db import SessionLocal  # noqa: E402
from Backend.models import (  # noqa: E402
    Assignment, Bid, CourierOffer, Escrow, Proof, Rating, Request, User,
)
from Backend.services.courier_trust import get_courier_trust  # noqa: E402

API = os.getenv("DEMO_API_URL", "http://localhost:8000")
TAG = "[דמו]"
WALLET_PREFIX = "DEMO-"

# Central Tel Aviv: all demo couriers start here, so only trust separates them
START = (32.0853, 34.7818)
# Demo history route: Azrieli -> Ramat Gan (~1.4 km)
ROUTE = (32.0745, 34.7917, 32.0838, 34.8013)

# name, description, customer score per delivery, minutes per delivery, past deliveries,
# courier profile (age, vehicle_type, vehicle_condition 0 poor / 1 ok / 2 good)
COURIERS = [
    ("דנה", "ותיקה, מדויקת בזמנים", 5, 12, 25, (27, "scooter", 2)),
    ("יוסי", "ותיק, מאחר הרבה", 3, 60, 25, (38, "motorcycle", 0)),
    ("נועה", "שליחה חדשה", None, None, 0, (22, "electric_scooter", 2)),
]


def _demo_users(db):
    return db.query(User).filter(User.wallet_address.like(f"{WALLET_PREFIX}%")).all()


def add():
    db = SessionLocal()
    try:
        if _demo_users(db):
            print("Demo data already exists. Run 'remove' first to start over.")
            return

        now = datetime.now(timezone.utc)
        sender = User(wallet_address=f"{WALLET_PREFIX}{uuid.uuid4().hex}", role="sender",
                      first_name=f"{TAG} לקוח", last_name="היסטוריה")
        db.add(sender)
        db.flush()

        for name, desc, score, minutes, count, (age, vehicle, condition) in COURIERS:
            d = User(wallet_address=f"{WALLET_PREFIX}{uuid.uuid4().hex}", role="driver",
                     first_name=f"{TAG} {name}", last_name=desc,
                     age=age, vehicle_type=vehicle, vehicle_condition=condition)
            db.add(d)
            db.flush()

            for i in range(count):
                # Spread over the last 10 days, at 13:00 Israel time
                start = (now - timedelta(days=1 + i % 10)).replace(hour=10, minute=0, second=0, microsecond=0)
                req = Request(
                    owner_user_id=sender.id, type="package", status="completed",
                    from_address=f"{TAG} עזריאלי", to_address=f"{TAG} רמת גן",
                    from_lat=ROUTE[0], from_lon=ROUTE[1], to_lat=ROUTE[2], to_lon=ROUTE[3],
                    window_start=start, window_end=start + timedelta(hours=2),
                    notes=f"{TAG} משלוח היסטוריה לדמו",
                )
                db.add(req)
                db.flush()
                asn = Assignment(
                    request_id=req.id, driver_user_id=d.id, agreed_price_cents=2000,
                    status="completed", assigned_at=start,
                    picked_up_at=start + timedelta(minutes=2),
                    completed_at=start + timedelta(minutes=minutes),
                )
                db.add(asn)
                db.flush()
                db.add(Rating(rater_user_id=sender.id, ratee_user_id=d.id,
                              assignment_id=asn.id, score=score, comment=f"{TAG}"))
            if count:
                d.rating = score

            db.add(CourierOffer(
                driver_user_id=d.id, from_address=f"{TAG} מרכז תל אביב",
                from_lat=START[0], from_lon=START[1],
                window_start=now - timedelta(hours=1), window_end=now + timedelta(days=14),
                min_price=20, types=["package", "passenger", "ride"], status="active",
                notes=f"{TAG} הצעת שליח לדמו",
            ))
        db.commit()
        print("Demo data added.")
    finally:
        db.close()
    status()


def status():
    db = SessionLocal()
    try:
        drivers = [u for u in _demo_users(db) if u.role == "driver"]
        if not drivers:
            print("No demo data. Run 'add'.")
            return
        for d in drivers:
            t = get_courier_trust(db, d.id)
            offers = db.query(CourierOffer).filter(CourierOffer.driver_user_id == d.id,
                                                   CourierOffer.status == "active").count()
            print(f"{d.first_name} ({d.last_name}, age {d.age}, {d.vehicle_type}, "
                  f"condition {d.vehicle_condition}): trust {t['trust_score']} "
                  f"| ratings {t['num_ratings']} | customers {int(t['customer_weight']*100)}% "
                  f"/ model {int(t['model_weight']*100)}% | active offers {offers}")
    finally:
        db.close()


def complete():
    """The demo courier picks up, drives and delivers your latest matched request (via the API)."""
    db = SessionLocal()
    try:
        demo_ids = [u.id for u in _demo_users(db)]
        asn = (
            db.query(Assignment).join(Request, Request.id == Assignment.request_id)
            .filter(Assignment.driver_user_id.in_(demo_ids),
                    Assignment.status.in_(["created", "picked_up", "in_transit"]),
                    ~Request.owner_user_id.in_(demo_ids))
            .order_by(Assignment.assigned_at.desc()).first()
        )
        if not asn:
            print("No open delivery with a demo courier. Create a request in the app first.")
            return
        aid, status_now = str(asn.id), str(asn.status)
    finally:
        db.close()

    steps = ["picked_up", "in_transit", "completed"]
    for st in steps[steps.index(status_now) + 1 if status_now in steps else 0:]:
        r = requests.patch(f"{API}/assignments/{aid}/status", json={"status": st}, timeout=30)
        print(f"{st}: HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text[:300])
            return
    print("Delivery completed. Refresh the delivery screen in the app to rate the courier.")


def remove():
    db = SessionLocal()
    try:
        users = _demo_users(db)
        ids = [u.id for u in users]
        if not ids:
            print("No demo data.")
            return
        asns = db.query(Assignment).filter(Assignment.driver_user_id.in_(ids)).all()
        asn_ids = [a.id for a in asns]
        # Your own requests that a demo courier took: cancel them (they cannot be finished without the demo courier)
        own_reqs = [a.request_id for a in asns]
        for model in (Rating, Proof, Escrow):
            db.query(model).filter(model.assignment_id.in_(asn_ids)).delete(synchronize_session=False)
        db.query(Rating).filter(Rating.rater_user_id.in_(ids) | Rating.ratee_user_id.in_(ids)).delete(synchronize_session=False)
        db.query(Assignment).filter(Assignment.id.in_(asn_ids)).delete(synchronize_session=False)
        db.query(Bid).filter(Bid.bidder_user_id.in_(ids)).delete(synchronize_session=False)
        db.query(Request).filter(Request.owner_user_id.in_(ids)).delete(synchronize_session=False)
        cancelled = (
            db.query(Request).filter(Request.id.in_(own_reqs), ~Request.owner_user_id.in_(ids))
            .update({Request.status: "cancelled"}, synchronize_session=False)
        )
        db.query(CourierOffer).filter(CourierOffer.driver_user_id.in_(ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        print(f"Removed {len(ids)} demo users and all their demo rows. "
              f"{cancelled} of your requests taken by a demo courier were set to 'cancelled'.")
    finally:
        db.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    actions = {"add": add, "status": status, "complete": complete, "remove": remove}
    if cmd not in actions:
        print(__doc__)
        sys.exit(1)
    actions[cmd]()
