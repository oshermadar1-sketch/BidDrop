# Backend/services/routing.py
# Road distance and driving time between two points, from OpenStreetMap routing (OSRM).
#
# The rest of the backend historically used the straight-line ("air") distance. Road
# distance is what a courier actually drives, so matching and pricing use it when it is
# available. Two rules keep the API independent of the routing server (BID-113):
#   * every lookup falls back to the air distance when the server fails or is slow, and
#   * after a failure the server is skipped for a cool-down period instead of retried
#     on every call.
#
# The delivery-time model (ml_predictor.py) also uses the road distance: it was trained
# on road distances of the same routes (preprocess.py, Zomato_Road_Distances.csv).
#
# Environment:
#   ROUTING_PROVIDER      "osrm" (default) or "air" (never call the network)
#   OSRM_BASE_URL         default https://router.project-osrm.org (public demo server)
#   ROUTING_TIMEOUT_SEC   per-request timeout, default 4
#   ROUTING_COOLDOWN_SEC  how long to use air distance after a failure, default 60
from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple, Union

import requests

log = logging.getLogger("routing")

PROVIDER = os.getenv("ROUTING_PROVIDER", "osrm").strip().lower()
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
TIMEOUT_SEC = float(os.getenv("ROUTING_TIMEOUT_SEC", "4"))
COOLDOWN_SEC = float(os.getenv("ROUTING_COOLDOWN_SEC", "60"))

# Speed assumed for the fallback duration when only the air distance is known.
AIR_SPEED_KMH = 30.0
# The public OSRM server limits table requests to this many points.
MAX_TABLE_POINTS = 100

Coord = Tuple[float, float]  # (lat, lon)


@dataclass(frozen=True)
class RouteLeg:
    distance_km: float
    duration_min: float
    source: str  # "osrm" or "air"


def air_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in km (haversine)."""
    lat1, lon1, lat2, lon2 = map(math.radians, map(float, (lat1, lon1, lat2, lon2)))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _air_leg(a: Coord, b: Coord) -> RouteLeg:
    km = air_km(a[0], a[1], b[0], b[1])
    return RouteLeg(km, 60.0 * km / AIR_SPEED_KMH, "air")


def _key(p: Coord) -> Coord:
    # ~1 m precision is plenty for caching.
    return (round(float(p[0]), 5), round(float(p[1]), 5))


_cache: Dict[Tuple[Coord, Coord], RouteLeg] = {}
_cache_max = 5000
_lock = threading.Lock()
_down_until = 0.0


def _available() -> bool:
    return PROVIDER == "osrm" and time.time() >= _down_until


def _mark_down(reason: Union[Exception, str]) -> None:
    global _down_until
    _down_until = time.time() + COOLDOWN_SEC
    log.warning("Routing server unavailable (%s); using air distance for %.0fs", reason, COOLDOWN_SEC)


def _put(k: Tuple[Coord, Coord], leg_value: RouteLeg) -> None:
    with _lock:
        if len(_cache) >= _cache_max:
            _cache.clear()
        _cache[k] = leg_value


def _get(url: str, params: dict) -> dict:
    """One GET to the routing server; raises on any non-Ok answer."""
    resp = requests.get(url, params=params, timeout=TIMEOUT_SEC,
                        headers={"User-Agent": "biddrop-backend"})
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM code={data.get('code')}")
    return data


def leg(lat1: float, lon1: float, lat2: float, lon2: float) -> RouteLeg:
    """Road distance and driving time from (lat1, lon1) to (lat2, lon2)."""
    a, b = _key((lat1, lon1)), _key((lat2, lon2))
    if a == b:
        return RouteLeg(0.0, 0.0, "osrm" if _available() else "air")
    k = (a, b)
    with _lock:
        hit = _cache.get(k)
    if hit is not None:
        return hit
    if not _available():
        return _air_leg(a, b)
    try:
        data = _get(f"{OSRM_BASE_URL}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}",
                    {"overview": "false"})
        r = data["routes"][0]
        out = RouteLeg(float(r["distance"]) / 1000.0, float(r["duration"]) / 60.0, "osrm")
    except Exception as e:  # network, HTTP, JSON or an answer without a route
        _mark_down(e)
        return _air_leg(a, b)
    _put(k, out)
    return out


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return leg(lat1, lon1, lat2, lon2).distance_km


def matrix(points: Sequence[Coord]) -> List[List[RouteLeg]]:
    """All-pairs legs for a small set of points, in one request where possible."""
    pts = [_key(p) for p in points]
    n = len(pts)
    if n == 0:
        return []
    if n > MAX_TABLE_POINTS or not _available():
        return [[leg(*pts[i], *pts[j]) for j in range(n)] for i in range(n)]
    try:
        coords = ";".join(f"{lon},{lat}" for lat, lon in pts)
        data = _get(f"{OSRM_BASE_URL}/table/v1/driving/{coords}",
                    {"annotations": "distance,duration"})
        dists, durs = data["distances"], data["durations"]
    except Exception as e:
        _mark_down(e)
        return [[_air_leg(pts[i], pts[j]) for j in range(n)] for i in range(n)]
    out: List[List[RouteLeg]] = []
    for i in range(n):
        row: List[RouteLeg] = []
        for j in range(n):
            d, t = dists[i][j], durs[i][j]
            if d is None or t is None:  # no road between the points (e.g. off the map)
                row.append(_air_leg(pts[i], pts[j]))
            else:
                cell = RouteLeg(float(d) / 1000.0, float(t) / 60.0, "osrm")
                _put((pts[i], pts[j]), cell)
                row.append(cell)
        out.append(row)
    return out


def reset_for_tests() -> None:
    global _down_until
    with _lock:
        _cache.clear()
    _down_until = 0.0
