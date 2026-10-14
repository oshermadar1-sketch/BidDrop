# app/auction/clearing_engine.py
# IDA* adapter for BidDrop double-auction clearing (bids-aware) with partial matching support.
from dataclasses import dataclass
from typing import List, Tuple, Dict, Iterable, Optional
from math import radians, sin, cos, sqrt, atan2, inf

from .ida_star_core import ida_star

# ----------------------------- Domain models -----------------------------
@dataclass(frozen=True)
class Point:
  lat: float
  lon: float

@dataclass(frozen=True)
class Ask:  # Sender request
  id: str                     # UUID as string
  pickup: Point
  dropoff: Point
  size: float                 # "passengers" or package size (we treat as 1.0 if unknown)
  max_price: float            # sender's budget ceiling
  window_start: Optional[float] = None   # epoch minutes (optional)
  window_end: Optional[float] = None     # epoch minutes (optional)

@dataclass(frozen=True)
class DriverState:
  driver_id: str              # UUID as string
  pos: Point
  time_min: float             # current driver time in minutes (epoch or relative)
  capacity_left: float
  rating: float               # 0..5

@dataclass(frozen=True)
class AssignStepCost:
  distance_km: float
  eta_min: float
  driver_price: float
  rating_penalty: float

  @property
  def penalty(self) -> float:
    return self.distance_km + self.eta_min + self.driver_price + self.rating_penalty

@dataclass(frozen=True)
class Weights:
  # Non-negative penalty weights. We minimize their weighted sum.
  w_dist: float = 1.0
  w_eta: float = 1.0
  w_price: float = 1.0
  w_rating_penalty: float = 0.0

# ----------------------------- Problem state -----------------------------
from typing import Tuple as Tup
@dataclass(frozen=True)
class State:
  assigned_mask: int
  drivers: Tup[DriverState, ...]

# ----------------------------- Utilities -----------------------------
EARTH_R_KM = 6371.0
def haversine_km(a: Point, b: Point) -> float:
  dlat = radians(b.lat - a.lat)
  dlon = radians(b.lon - a.lon)
  la1 = radians(a.lat)
  la2 = radians(b.lat)
  h = sin(dlat/2)**2 + cos(la1)*cos(la2)*sin(dlon/2)**2
  return 2 * EARTH_R_KM * atan2(sqrt(h), sqrt(1 - h))

def travel_eta_min(dist_km: float, avg_kmh: float) -> float:
  if avg_kmh <= 0:
    return inf
  return 60.0 * (dist_km / avg_kmh)

def quantize_state(ds: DriverState) -> tuple:
  return (
    ds.driver_id,
    round(ds.pos.lat, 3), round(ds.pos.lon, 3),
    int(ds.time_min // 5),
    round(ds.capacity_left, 1),
  )

# ----------------------------- Feasibility -----------------------------
def feasible(d: DriverState, ask: Ask, now_min: float, avg_kmh: float) -> bool:
  """Hard constraints before simulating assign."""
  if d.capacity_left < ask.size:
    return False
  # Optional time-window feasibility (optimistic)
  pk_dist = haversine_km(d.pos, ask.pickup)
  leg1 = travel_eta_min(pk_dist, avg_kmh)
  dl_dist = haversine_km(ask.pickup, ask.dropoff)
  leg2 = travel_eta_min(dl_dist, avg_kmh)
  optimistic_arrival = now_min + leg1 + leg2
  if ask.window_end is not None and optimistic_arrival > ask.window_end:
    return False
  return True

# ----------------------------- Heuristic (admissible) -----------------------------
def lower_bound_remaining(
  asks: List[Ask],
  drivers: Tup[DriverState, ...],
  assigned_mask: int,
  avg_kmh: float,
  weights: Weights,
  price_lb_per_ask: Optional[List[float]] = None,
  rating_max: float = 5.0,
  allow_partial: bool = True,
  unassigned_penalty: float = 0.0,
) -> float:
  """
  Sum, over unassigned asks, of the BEST-CASE weighted penalty:
    min( best-possible assign to any driver , unassigned_penalty if skipping is allowed ).
  This keeps the heuristic admissible when partial matching is enabled.
  """
  lb_total = 0.0
  for i, a in enumerate(asks):
    if (assigned_mask >> i) & 1:
      continue

    best_assign = inf
    for d in drivers:
      d1_km = haversine_km(d.pos, a.pickup)
      d2_km = haversine_km(a.pickup, a.dropoff)
      dist_km = d1_km + d2_km
      eta_min = travel_eta_min(dist_km, avg_kmh)
      price_lb = price_lb_per_ask[i] if price_lb_per_ask is not None else 0.0
      rating_penalty = max(0.0, (rating_max - d.rating))
      penalty = (
        weights.w_dist * dist_km +
        weights.w_eta * eta_min +
        weights.w_price * price_lb +
        weights.w_rating_penalty * rating_penalty
      )
      if penalty < best_assign:
        best_assign = penalty

    if allow_partial:
      lb_total += min(best_assign, max(0.0, unassigned_penalty))
    else:
      lb_total += best_assign
  return lb_total

# ----------------------------- IDA* adapter (BIDS-AWARE + PARTIAL) -----------------------------
def solve_clearing_ida(
  asks: List[Ask],
  initial_drivers: List[DriverState],
  avg_kmh: float,
  weights: Weights,
  rating_max: float,
  # only bidders allowed per ask (indices into initial_drivers)
  allowed_drivers_per_ask: Optional[List[List[int]]] = None,
  # revealed bid amount per (ask_idx, driver_idx), if exists
  bid_amounts: Optional[Dict[Tuple[int, int], float]] = None,
  # Optional: price LB per ask (e.g., min revealed bid for that ask)
  price_lb_per_ask: Optional[List[float]] = None,
  # NEW: partial matching flags
  allow_partial: bool = True,
  unassigned_penalty: float = 0.0,
) -> Tuple[Optional[List[Tuple[int, int]]], float, Dict]:
  """
  Returns:
    - plan: list of (ask_index, driver_index) *only for assigned pairs* (skips are omitted)
    - total_cost: minimal weighted penalty (including skip penalties)
    - debug: dict with small stats
  Notes:
    - When allow_partial=True, expansion includes a "skip" move with cost=unassigned_penalty.
    - Heuristic accounts for skip cost to remain admissible.
  """
  ALL = (1 << len(asks)) - 1
  init_state = State(assigned_mask=0, drivers=tuple(initial_drivers))
  parent: Dict[State, Tuple[State, Tuple[int, int], float]] = {}

  def h(s: State) -> float:
    return lower_bound_remaining(
      asks, s.drivers, s.assigned_mask, avg_kmh, weights,
      price_lb_per_ask=price_lb_per_ask, rating_max=rating_max,
      allow_partial=allow_partial, unassigned_penalty=unassigned_penalty
    )

  def is_goal(s: State) -> bool:
    # Goal is when we've made a *decision* (assign or skip) for every ask.
    return s.assigned_mask == ALL

  def next_unassigned(mask: int) -> int:
    for i in range(len(asks)):
      if ((mask >> i) & 1) == 0:
        return i
    return -1

  def expand(s: State) -> Iterable[Tuple[State, float]]:
    i = next_unassigned(s.assigned_mask)
    if i < 0:
      return []
    a = asks[i]
    outs: List[Tuple[State, float]] = []

    # 1) Try assigning ask i to allowed drivers (if feasible)
    driver_indices = (
      allowed_drivers_per_ask[i]
      if allowed_drivers_per_ask is not None
      else list(range(len(s.drivers)))
    )
    for dj in driver_indices:
      d = s.drivers[dj]
      if not feasible(d, a, now_min=d.time_min, avg_kmh=avg_kmh):
        continue

      # Distance & ETA
      d1_km = haversine_km(d.pos, a.pickup)
      d2_km = haversine_km(a.pickup, a.dropoff)
      dist_km = d1_km + d2_km
      eta_min = travel_eta_min(dist_km, avg_kmh)

      # Price: use revealed bid if provided; else 0 in step-cost (heuristic may include LB)
      step_price = 0.0
      if bid_amounts is not None:
        step_price = bid_amounts.get((i, dj), 0.0)

      rating_penalty = max(0.0, (rating_max - d.rating))

      delta_cost = (
        weights.w_dist * dist_km +
        weights.w_eta * eta_min +
        weights.w_price * step_price +
        weights.w_rating_penalty * rating_penalty
      )

      new_d = DriverState(
        driver_id=d.driver_id,
        pos=a.dropoff,
        time_min=d.time_min + eta_min,
        capacity_left=max(0.0, d.capacity_left - a.size),
        rating=d.rating,
      )

      new_drivers = list(s.drivers)
      new_drivers[dj] = new_d
      s2 = State(assigned_mask=(s.assigned_mask | (1 << i)), drivers=tuple(new_drivers))
      outs.append((s2, delta_cost))
      parent[s2] = (s, (i, dj), delta_cost)

    # 2) Optional: skip ask i (partial matching)
    if allow_partial:
      s_skip = State(assigned_mask=(s.assigned_mask | (1 << i)), drivers=s.drivers)
      skip_cost = max(0.0, unassigned_penalty)
      outs.append((s_skip, skip_cost))
      parent[s_skip] = (s, (i, -1), skip_cost)

    return outs

  def key(s: State):
    return (s.assigned_mask, tuple(quantize_state(d) for d in s.drivers))

  goal, best_cost = ida_star(init_state, h, expand, is_goal, key)
  if goal is None:
    return None, inf, {"expanded": 0, "matched": 0, "skipped": 0}

  # Reconstruct plan (omit skips where driver_index == -1)
  plan_pairs: List[Tuple[int, int]] = []
  matched = 0
  skipped = 0
  cur = goal
  while cur != init_state:
    prev, (ask_i, drv_j), _dc = parent[cur]
    if drv_j >= 0:
      plan_pairs.append((ask_i, drv_j))
      matched += 1
    else:
      skipped += 1
    cur = prev
  plan_pairs.reverse()

  debug = {"expanded": len(plan_pairs), "matched": matched, "skipped": skipped}
  return plan_pairs, best_cost, debug
