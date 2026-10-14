"""
Matching end to end on a real PostgreSQL test database.
Runs only when TEST_DATABASE_URL is set (an empty throwaway DB; tables are created and dropped).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

if TEST_DATABASE_URL:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from Backend.Database.schema_upgrades import apply_schema_upgrades
    from Backend.models import Assignment, Base, CourierOffer, Rating, Request, User
    from Backend.services.courier_trust import get_courier_trust
    from Backend.services.matching import match_for_request
    from Backend.trust_score import PRIORS

NOW = datetime.now(timezone.utc)
PICKUP = (32.0745, 34.7917)
DROPOFF = (32.0838, 34.8013)


@pytest.fixture()
def Session():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    apply_schema_upgrades(engine)  # same columns the server adds at startup
    yield sessionmaker(bind=engine)
    Base.metadata.drop_all(engine)
    engine.dispose()


def _user(db, role, **kw):
    u = User(wallet_address=f"0x{uuid.uuid4().hex}", role=role, **kw)
    db.add(u)
    db.flush()
    return u


def _request(db, owner, status="open", **kw):
    r = Request(
        owner_user_id=owner.id, type="package", status=status,
        from_lat=PICKUP[0], from_lon=PICKUP[1], to_lat=DROPOFF[0], to_lon=DROPOFF[1], **kw,
    )
    db.add(r)
    db.flush()
    return r


def _history(db, sender, driver, score, minutes, count):
    """`count` completed deliveries of `driver`, each taking `minutes` and rated `score`."""
    for _ in range(count):
        req = _request(db, sender, status="completed")
        asn = Assignment(
            request_id=req.id, driver_user_id=driver.id, agreed_price_cents=1000,
            status="completed", assigned_at=NOW - timedelta(days=1),
            completed_at=NOW - timedelta(days=1) + timedelta(minutes=minutes),
        )
        db.add(asn)
        db.flush()
        db.add(Rating(rater_user_id=sender.id, ratee_user_id=driver.id, assignment_id=asn.id, score=score))


def _offer(db, driver, lat, lon):
    o = CourierOffer(
        driver_user_id=driver.id, from_address="x", from_lat=lat, from_lon=lon,
        window_start=NOW - timedelta(hours=1), window_end=NOW + timedelta(hours=5),
        min_price=10, types=["package"], status="active",
    )
    db.add(o)
    return o


def test_new_driver_gets_typical_score(Session):
    with Session() as db:
        d = _user(db, "driver")
        db.commit()
        t = get_courier_trust(db, d.id)
    assert t["num_ratings"] == 0
    assert t["trust_score"] == pytest.approx(PRIORS["typical_model_score"], abs=0.01)


def test_history_is_read_from_db(Session):
    with Session() as db:
        sender = _user(db, "sender")
        d = _user(db, "driver")
        _history(db, sender, d, score=4, minutes=200, count=3)  # very late deliveries
        db.commit()
        t = get_courier_trust(db, d.id)
    assert t["num_ratings"] == 3
    assert t["customer_part"] == 4
    assert t["num_timed_deliveries"] == 3
    assert t["model_part"] < PRIORS["typical_model_score"]


def test_matching_prefers_trusted_driver(Session):
    with Session() as db:
        sender = _user(db, "sender")
        good = _user(db, "driver", rating=5)
        bad = _user(db, "driver", rating=2)
        _history(db, sender, good, score=5, minutes=10, count=20)
        _history(db, sender, bad, score=2, minutes=120, count=20)
        # Both start at the same place, so only trust separates them
        _offer(db, bad, *PICKUP)
        _offer(db, good, *PICKUP)
        req = _request(db, sender, window_start=NOW, window_end=NOW + timedelta(hours=2))
        db.commit()
        req_id, good_id = req.id, good.id

    with Session() as db:
        asn = match_for_request(db, request_id=req_id)
        assert asn is not None
        assert asn.driver_user_id == good_id


def test_matching_prefers_nearby_driver_when_trust_is_equal(Session):
    with Session() as db:
        sender = _user(db, "sender")
        near = _user(db, "driver")
        far = _user(db, "driver")
        _offer(db, far, 32.32, 34.85)  # Netanya, ~30 km away
        _offer(db, near, *PICKUP)
        req = _request(db, sender, window_start=NOW, window_end=NOW + timedelta(hours=2))
        db.commit()
        req_id, near_id = req.id, near.id

    with Session() as db:
        asn = match_for_request(db, request_id=req_id)
        assert asn.driver_user_id == near_id


def test_assignment_details_show_trust_eta_and_rating(Session):
    from Backend.routes_assignments import _pack_assignment_detail

    with Session() as db:
        sender = _user(db, "sender")
        d = _user(db, "driver")
        _history(db, sender, d, score=4, minutes=10, count=1)
        asn = db.query(Assignment).filter(Assignment.driver_user_id == d.id).one()

        out = _pack_assignment_detail(db, asn)
        assert out.driver.trust_score is not None
        assert out.driver.num_ratings == 1
        assert out.driver.is_new_courier
        assert 5 < out.predicted_minutes < 60
        assert out.driver_rating_score == 4
        assert out.driver.customer_weight + out.driver.model_weight == pytest.approx(1, abs=0.011)
        assert out.driver.num_timed_deliveries == 1


def test_suspiciously_fast_delivery_is_not_counted(Session):
    with Session() as db:
        sender = _user(db, "sender")
        d = _user(db, "driver")
        _history(db, sender, d, score=5, minutes=1, count=3)  # "delivered" after 1 minute
        db.commit()
        t = get_courier_trust(db, d.id)
    assert t["num_ratings"] == 3            # the ratings still count
    assert t["num_timed_deliveries"] == 0   # the times do not
    assert t["model_part"] == pytest.approx(PRIORS["typical_model_score"], abs=0.01)


def test_schema_upgrade_adds_profile_columns_and_is_repeatable(Session):
    from sqlalchemy import inspect, text
    from Backend.Database.schema_upgrades import apply_schema_upgrades

    engine = Session.kw["bind"]
    with engine.begin() as c:  # simulate an old database without the new columns
        for col in ("age", "vehicle_type", "vehicle_condition"):
            c.execute(text(f"ALTER TABLE users DROP COLUMN {col}"))
    apply_schema_upgrades(engine)
    apply_schema_upgrades(engine)  # second run changes nothing
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"age", "vehicle_type", "vehicle_condition"} <= cols


def test_matching_uses_courier_profile_when_trust_is_equal(Session):
    with Session() as db:
        sender = _user(db, "sender")
        fast = _user(db, "driver", age=22, vehicle_type="electric_scooter", vehicle_condition=2)
        slow = _user(db, "driver", age=38, vehicle_type="motorcycle", vehicle_condition=0)
        _offer(db, slow, *PICKUP)
        _offer(db, fast, *PICKUP)
        req = _request(db, sender, window_start=NOW, window_end=NOW + timedelta(hours=2))
        db.commit()
        req_id, fast_id = req.id, fast.id

    with Session() as db:
        asn = match_for_request(db, request_id=req_id)
        assert asn.driver_user_id == fast_id


def _auction_offer(db, driver, price):
    db.add(CourierOffer(
        driver_user_id=driver.id, from_address="x", from_lat=PICKUP[0], from_lon=PICKUP[1],
        window_start=NOW - timedelta(hours=1), window_end=NOW + timedelta(hours=5),
        min_price=price, types=["package"], status="active",
    ))


def test_auction_assigns_and_prefers_trusted_driver(Session):
    from Backend.routes_auction import run_clearing_tick

    with Session() as db:
        sender = _user(db, "sender")
        good = _user(db, "driver")
        bad = _user(db, "driver")
        _history(db, sender, good, score=5, minutes=10, count=20)
        _history(db, sender, bad, score=2, minutes=120, count=20)
        _auction_offer(db, bad, 20)
        _auction_offer(db, good, 20)
        req = _request(db, sender, window_start=NOW, window_end=NOW + timedelta(hours=2), max_price=50)
        db.commit()
        req_id, good_id = req.id, good.id

    with Session() as db:
        res = run_clearing_tick(db)
        assert res["cleared"], res
        asn = db.query(Assignment).filter(Assignment.request_id == req_id).one()
        assert asn.driver_user_id == good_id
        assert asn.agreed_price_cents == 2000


def test_auction_trust_outweighs_small_price_difference(Session):
    from Backend.routes_auction import run_clearing_tick

    with Session() as db:
        sender = _user(db, "sender")
        good = _user(db, "driver")
        bad = _user(db, "driver")
        _history(db, sender, good, score=5, minutes=10, count=20)
        _history(db, sender, bad, score=2, minutes=120, count=20)
        _auction_offer(db, bad, 20)    # 5 NIS cheaper, but much less trusted
        _auction_offer(db, good, 25)
        req = _request(db, sender, window_start=NOW, window_end=NOW + timedelta(hours=2), max_price=50)
        db.commit()
        req_id, good_id = req.id, good.id

    with Session() as db:
        assert run_clearing_tick(db)["cleared"]
        asn = db.query(Assignment).filter(Assignment.request_id == req_id).one()
        assert asn.driver_user_id == good_id
