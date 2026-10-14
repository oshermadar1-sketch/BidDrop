# -----------------------------------------------------------------------------
# Auto-matching pipeline for BidDrop:
# When a request or an offer is created in the backend, we "poke" this module
# to run a short pipeline:
#   1) GET   /poba/requests-open
#   2) GET   /poba/offers-active
#   3) POST  /poba/build-proposal       ← IDA*-based builder (same as your curl)
#   4) POST  /poba/submit-proposal      ← submit to the chain (PoBA pallet)
#   5) POST  /poba/finalize-slot        ← finalize the slot on-chain
#   6) POST  /poba/apply-proposal       ← (optional) create DB assignments
#
# Notes:
# - This file only orchestrates endpoints. Business logic stays in your routes.
# - Debounce + a run-lock prevent flooding and overlapping runs.
#
# Env vars:
#   BID_AUTO_MATCH=1                       → enable background runner (default off)
#   AUTO_MATCH_BASE=http://127.0.0.1:8000  → FastAPI base
#   BID_AUTO_DEBOUNCE_SEC=3                → min seconds between runs
#   BID_AUTO_APPLY=1                       → if set, call /poba/apply-proposal after finalize
#   # optional prefilter caps (passed to /build-proposal if set and >0)
#   POBA_MAX_START_KM=0
#   POBA_MAX_END_KM=0
#   POBA_MAX_TOTAL_KM=0
#
# Dependencies:
#   pip install requests
# -----------------------------------------------------------------------------

from __future__ import annotations
import os
import time
import threading
from typing import Any, Dict

import requests  # lightweight HTTP client

# ---- configuration from env ----
AUTO_BASE = os.getenv("AUTO_MATCH_BASE", "http://127.0.0.1:8000").rstrip("/")
AUTO_ENABLED = os.getenv("BID_AUTO_MATCH", "0").lower() not in {"0", "", "false", "no"}
DEBOUNCE_SEC = int(os.getenv("BID_AUTO_DEBOUNCE_SEC", "3"))
DO_APPLY = os.getenv("BID_AUTO_APPLY", "0").lower() not in {"0", "", "false", "no"}

# optional distance caps (if >0, will be forwarded to /build-proposal)
_CAP_START = float(os.getenv("POBA_MAX_START_KM", "0") or "0")
_CAP_END   = float(os.getenv("POBA_MAX_END_KM", "0") or "0")
_CAP_TOTAL = float(os.getenv("POBA_MAX_TOTAL_KM", "0") or "0")

# ---- simple mutexes & last-run timestamp ----
_gate_lock = threading.Lock()     # gate for debounce
_run_lock = threading.Lock()      # ensure only one pipeline runs at a time
_last_run_ts: float = 0.0

# ---- tiny helpers ----
def _get_json(url: str) -> Any:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()

def _post_json(url: str, payload: Dict[str, Any]) -> Any:
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def _now() -> float:
    return time.time()

def _log(*args: Any) -> None:
    print("[auto-match]", *args)


def _get_current_slot() -> int:
    """
    Derive the current PoBA slot from /poba/chain-health.

    We reuse the same logic as the manual curl script:
    - Call /poba/chain-health
    - Read best_header.result.number (hex string, e.g. "0x1a")
    - Convert it to an integer and use it as the slot.

    If anything fails, we fall back to a time-based slot to avoid crashing
    the pipeline, but that is not ideal for PoBA semantics.
    """
    try:
        data = _get_json(f"{AUTO_BASE}/poba/chain-health")
        # Expected shape: {"best_header": {"result": {"number": "0x..." }}, ...}
        best_header = data.get("best_header") or {}
        result = best_header.get("result") or {}
        hex_num = result.get("number")

        if isinstance(hex_num, str) and hex_num.startswith("0x"):
            slot = int(hex_num, 16)
            _log("current slot from chain-health:", slot)
            return slot

        # If number is already an int-like, try to cast directly
        if isinstance(hex_num, (int, float)):
            slot = int(hex_num)
            _log("current slot from chain-health (non-hex):", slot)
            return slot

        _log("chain-health did not contain a valid best_header.result.number:", hex_num)

    except Exception as e:
        _log("failed to derive slot from chain-health, falling back to time-based slot:", repr(e))

    # Fallback: this keeps pipeline alive but is not PoBA-ideal
    fallback_slot = int(_now())
    _log("using fallback time-based slot:", fallback_slot)
    return fallback_slot


# ---- the public entrypoint you will call from your routes ----
def try_auto_match() -> None:
    """
    Fire-and-forget background trigger.
    Safe to call after creating a request or an offer.
    If disabled by env, returns immediately.
    Debounced + serialized (cheap fast path).
    """
    if not AUTO_ENABLED:
        return

    global _last_run_ts
    with _gate_lock:
        now = _now()
        if now - _last_run_ts < DEBOUNCE_SEC:
            return
        _last_run_ts = now

    # Run on a thread so we don't block the HTTP response
    t = threading.Thread(target=_run_pipeline, daemon=True)
    t.start()


def _run_pipeline() -> None:
    """
    The actual pipeline. Keep it robust and quiet: failures shouldn't crash the server.
    Prevent overlapping runs with a non-blocking run-lock.
    """
    if not _run_lock.acquire(blocking=False):
        _log("skip: pipeline already running")
        return

    try:
        # 1) Pull current market snapshot
        R = _get_json(f"{AUTO_BASE}/poba/requests-open")
        O = _get_json(f"{AUTO_BASE}/poba/offers-active")
        if not R or not O:
            _log("nothing to do: R=", len(R or []), "O=", len(O or []))
            return

        # 2) Build proposal (forward distance caps if configured)
        slot = _get_current_slot()  # ← FIX: use chain-based slot instead of time.time()
        build_body: Dict[str, Any] = {"slot": slot, "requests": R, "offers": O}
        if _CAP_START > 0:
            build_body["max_start_km"] = _CAP_START
        if _CAP_END > 0:
            build_body["max_end_km"] = _CAP_END
        if _CAP_TOTAL > 0:
            build_body["max_total_km"] = _CAP_TOTAL

        build = _post_json(f"{AUTO_BASE}/poba/build-proposal", build_body)

        matches = build.get("matches") or []
        if not matches:
            _log("build ok but no matches for slot", slot)
            return

        _log(f"built slot {slot} with {len(matches)} matches, total_score={build.get('total_score')}")

        # 3) Submit to chain (PoBA pallet)
        _post_json(f"{AUTO_BASE}/poba/submit-proposal", build)
        _log("submit-proposal sent")

        # 4) Finalize the slot
        _post_json(f"{AUTO_BASE}/poba/finalize-slot", {"slot": slot})
        _log("finalize-slot sent")

        # 5) Materialize to DB so the app sees assignments (optional flag)
        if DO_APPLY:
            _post_json(f"{AUTO_BASE}/poba/apply-proposal", build)
            _log("apply-proposal sent")
        else:
            _log("skipping apply-proposal (BID_AUTO_APPLY not enabled)")

    except Exception as e:
        # Don't raise; just log and exit quietly so the API continues to work.
        _log("pipeline error:", repr(e))
    finally:
        _run_lock.release()
