"""
Road-distance routing (services/routing.py) and its use by the auction.

No network: the OSRM call is replaced by a stub. The fallback rules are what matters
here, since the public routing server can be slow or down (BID-113).
"""
import pytest

from Backend.services import routing
from Backend.auction.clearing_engine import Ask, DriverState, Point, Weights, solve_clearing_ida

# Tel Aviv (Dizengoff Center) -> Ramat Gan (Ayalon mall): 5.4 km by air, about 6.2 by road.
A = (32.0753, 34.7748)
B = (32.0998, 34.8248)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    routing.reset_for_tests()
    monkeypatch.setattr(routing, "PROVIDER", "osrm")
    yield
    routing.reset_for_tests()


def _route_answer(meters, seconds):
    return {"code": "Ok", "routes": [{"distance": meters, "duration": seconds}]}


def test_leg_uses_the_road_distance(monkeypatch):
    monkeypatch.setattr(routing, "_get", lambda url, params: _route_answer(6200, 534))
    leg = routing.leg(*A, *B)
    assert leg.source == "osrm"
    assert leg.distance_km == pytest.approx(6.2)
    assert leg.duration_min == pytest.approx(8.9)


def test_leg_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(routing, "_get", lambda url, params: calls.append(url) or _route_answer(6200, 534))
    routing.leg(*A, *B)
    routing.leg(*A, *B)
    assert len(calls) == 1


def test_leg_falls_back_to_air_on_failure(monkeypatch):
    def boom(url, params):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(routing, "_get", boom)
    leg = routing.leg(*A, *B)
    assert leg.source == "air"
    assert leg.distance_km == pytest.approx(routing.air_km(*A, *B), rel=1e-6)
    assert leg.duration_min > 0


def test_after_a_failure_the_server_is_not_retried_during_cooldown(monkeypatch):
    calls = []
    def boom(url, params):
        calls.append(url)
        raise RuntimeError("timeout")
    monkeypatch.setattr(routing, "_get", boom)
    routing.leg(*A, *B)
    routing.leg(*B, *A)
    assert len(calls) == 1


def test_provider_air_never_calls_the_network(monkeypatch):
    monkeypatch.setattr(routing, "PROVIDER", "air")
    def boom(url, params):
        raise AssertionError("network call made")
    monkeypatch.setattr(routing, "_get", boom)
    assert routing.leg(*A, *B).source == "air"


def test_matrix_fills_unroutable_cells_with_air(monkeypatch):
    def table(url, params):
        return {"code": "Ok",
                "distances": [[0, 6200], [None, 0]],
                "durations": [[0, 534], [None, 0]]}
    monkeypatch.setattr(routing, "_get", table)
    m = routing.matrix([A, B])
    assert m[0][1].source == "osrm" and m[0][1].distance_km == pytest.approx(6.2)
    assert m[1][0].source == "air"
    assert m[0][0].distance_km == 0


def test_matrix_falls_back_entirely_on_failure(monkeypatch):
    def boom(url, params):
        raise RuntimeError("503")
    monkeypatch.setattr(routing, "_get", boom)
    m = routing.matrix([A, B])
    assert all(cell.source == "air" for row in m for cell in row)


def test_auction_uses_the_supplied_distance_function():
    asks = [Ask(id="r1", pickup=Point(*A), dropoff=Point(*B), size=1.0, max_price=100.0)]
    drivers = [DriverState(driver_id="d1", pos=Point(*A), time_min=0.0, capacity_left=1.0, rating=5.0)]
    seen = []
    def dist_fn(p, q):
        seen.append((p, q))
        return 6.2
    plan, cost, _ = solve_clearing_ida(
        asks=asks, initial_drivers=drivers, avg_kmh=40.0, weights=Weights(),
        rating_max=5.0, allow_partial=True, unassigned_penalty=10_000.0, dist_fn=dist_fn,
    )
    assert plan == [(0, 0)]
    assert seen, "the solver should have asked dist_fn for distances"
    # cost = w_dist * (6.2 + 6.2) + w_eta * eta(12.4 km at 40 km/h)
    assert cost == pytest.approx(12.4 + 60.0 * 12.4 / 40.0)
