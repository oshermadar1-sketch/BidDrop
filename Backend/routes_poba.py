# PoBA (Proof-of-Bid-Assignment) REST endpoints:
# - Pull open requests/offers from DB
# - Build a proposal (IDA*) with distance+price cost model
# - Submit proposal & finalize slot on a Substrate chain
#   (with priority-aware retry)
# - Optionally apply proposal into DB assignments (manual endpoints)
#
# New:
# - Background listener that watches PoBA::LastFinalizedSlot and, when it
#   advances, fetches FinalizedProposal(slot) and applies matches into the DB.

from fastapi import APIRouter, HTTPException, Depends, Body, Request, FastAPI
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Tuple, Annotated, Iterable, Optional
from uuid import UUID
import os, logging, math
from datetime import timezone
import time
from threading import Thread

from sqlalchemy.orm import Session
from sqlalchemy import text

from .Database.db import get_db
from .Database.db import SessionLocal  # for auto-apply and listener
from .models import Request as DbRequest, CourierOffer

from substrateinterface import SubstrateInterface, Keypair
try:
    from substrateinterface.exceptions import SubstrateRequestException
except Exception:
    class SubstrateRequestException(Exception):
        pass

from json.decoder import JSONDecodeError

from .auction.ida_star_core import ida_star

router = APIRouter(prefix="/poba", tags=["poba"])
log = logging.getLogger("poba")


# ------------------------------ Chain helpers ------------------------------

def _ws_url() -> str:
    return os.getenv("SUBSTRATE_WS_URL", "ws://127.0.0.1:9944")


def _type_registry_preset() -> str:
    return os.getenv("SUBSTRATE_TYPE_REGISTRY_PRESET", "substrate-node-template")


def _pallet_name() -> str:
    # IMPORTANT: the module name as appears in construct_runtime! is "PoBA"
    return os.getenv("POBA_PALLET", "PoBA")


def _call_submit() -> str:
    return os.getenv("POBA_CALL_SUBMIT", "submit_proposal")


def _call_finalize() -> str:
    return os.getenv("POBA_CALL_FINALIZE", "finalize_slot")


def _param_matches() -> str:
    # Some chains use "matches", others "match_items" – make it configurable.
    return os.getenv("POBA_PARAM_MATCHES", "matches")


def _escrow_pallet_name() -> str:
    """
    Name of the escrow pallet as it appears in construct_runtime!.
    Default: 'Escrow'.
    """
    return os.getenv("ESCROW_PALLET", "Escrow")


def _escrow_call_create() -> str:
    """
    Name of the create-escrow extrinsic in the Escrow pallet.
    Default: 'create_escrow'.
    """
    return os.getenv("ESCROW_CALL_CREATE", "create_escrow")


def _wait_for_finalization() -> bool:
    return os.getenv("POBA_WAIT_FINALIZATION", "0").lower() in {"1", "true", "yes"}


def _finalization_timeout_sec() -> int:
    # kept only for debug visibility; not passed to substrate.submit_extrinsic
    return int(os.getenv("POBA_FINALIZATION_TIMEOUT_SEC", "60"))


def _slot_poll_interval_sec() -> int:
    """
    How often the background listener polls LastFinalizedSlot (seconds).
    Default is 6 (שקול ל־block time).
    """
    return int(os.getenv("POBA_SLOT_POLL_SEC", "6"))


# ------------------------------ Types & utils ------------------------------

Hex32 = Annotated[str, Field(min_length=32, max_length=32, pattern=r"^[0-9a-fA-F]{32}$")]


def uuid_to_16_hex(u: UUID) -> str:
    return u.hex


def _hex32_to_uuid(s: str) -> UUID:
    # 32-hex (no dashes) -> UUID
    return UUID(hex=s)


def hex16_to_u8_array_16(s: str) -> List[int]:
    try:
        b = bytes.fromhex(s)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": "invalid_hex",
            "hint": "uuid_16 must be a 32-character hex string",
            "error": str(e),
        })
    if len(b) != 16:
        raise HTTPException(status_code=400, detail={
            "code": "invalid_length",
            "hint": "uuid_16 must encode exactly 16 bytes",
            "got": len(b),
        })
    return list(b)


def get_substrate() -> SubstrateInterface:
    """
    Create a fresh SubstrateInterface client.

    Using a new client per call avoids reusing a dead WebSocket connection
    and reduces the chance of BrokenPipe errors when the node restarts.
    """
    url = _ws_url()
    preset = _type_registry_preset()
    try:
        return SubstrateInterface(
            url=url,
            ss58_format=42,
            type_registry_preset=preset,
            auto_reconnect=True,
        )
    except Exception as e:
        log.exception("Failed to connect Substrate WS at %s: %s", url, e)
        raise HTTPException(status_code=502, detail={
            "code": "substrate_connect_failed",
            "ws_url": url,
            "preset": preset,
            "error": str(e),
            "hint": "Ensure node is running with WS on the given URL",
        })


def get_signer(proposer_id: Optional[str] = None) -> Keypair:
    """
    Resolve the signer (Keypair) for a given proposer_id.

    Resolution order:
    1) If proposer_id is provided:
       - SUBSTRATE_SIGNER_URI_<PROPOSER_ID_UPPER>
       - SUBSTRATE_SIGNER_MNEMONIC_<PROPOSER_ID_UPPER>
    2) Fallback to global:
       - SUBSTRATE_SIGNER_URI
       - SUBSTRATE_SIGNER_MNEMONIC
    """
    uri = None
    mnemonic = None

    # Per-proposer overrides (e.g. SUBSTRATE_SIGNER_URI_ALICE, SUBSTRATE_SIGNER_URI_BOB)
    if proposer_id:
        suffix = proposer_id.upper()
        uri = os.getenv(f"SUBSTRATE_SIGNER_URI_{suffix}")
        mnemonic = os.getenv(f"SUBSTRATE_SIGNER_MNEMONIC_{suffix}")

    # Global defaults
    if not uri:
        uri = os.getenv("SUBSTRATE_SIGNER_URI")
    if not mnemonic:
        mnemonic = os.getenv("SUBSTRATE_SIGNER_MNEMONIC")

    if uri:
        try:
            return Keypair.create_from_uri(uri)
        except Exception as e:
            raise HTTPException(status_code=400, detail={
                "code": "invalid_signer_uri",
                "error": str(e),
                "hint": "SUBSTRATE_SIGNER_URI(_<ID>) is not a valid SURI (e.g. //Alice)",
            })
    if mnemonic:
        try:
            return Keypair.create_from_mnemonic(mnemonic)
        except Exception as e:
            raise HTTPException(status_code=400, detail={
                "code": "invalid_signer_mnemonic",
                "error": str(e),
                "hint": "Provide a valid 12/24-word mnemonic or use SUBSTRATE_SIGNER_URI",
            })

    raise HTTPException(status_code=400, detail={
        "code": "signer_not_set",
        "hint": "Define SUBSTRATE_SIGNER_URI(_<ID>) or SUBSTRATE_SIGNER_MNEMONIC(_<ID>)",
    })


# ------------------------------ Schemas ------------------------------

class MarketRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    uuid_16: Hex32
    from_lat: int
    from_lon: int
    to_lat: int
    to_lon: int
    max_price_cents: int
    kind: int
    window_start: int
    window_end: int


class MarketOffer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    uuid_16: Hex32
    min_price_cents: int
    from_lat: int
    from_lon: int
    to_lat: int
    to_lon: int
    window_start: int
    window_end: int
    types_mask: int


class MatchItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    request_uuid: Hex32
    offer_uuid: Hex32
    agreed_price_cents: int
    partial_score: int


class SubmitProposalBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slot: Annotated[int, Field(ge=0)]
    # If client does not send total_score, default to 0 (we do not fabricate any other value).
    total_score: int = 0
    matches: List[MatchItem]


class FinalizeBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slot: Annotated[int, Field(ge=0)]


class BuildBody(BaseModel):
    """
    Compute a proposal for a given (requests, offers) snapshot.
    Optional distance caps allow pre-filtering pairs (good for large markets).
    """
    model_config = ConfigDict(extra="ignore")
    slot: Annotated[int, Field(ge=0)]
    requests: List[MarketRequest]
    offers: List[MarketOffer]

    # Optional soft caps (km). If provided, pairs exceeding thresholds are discarded.
    max_start_km: Optional[float] = Field(default=None, ge=0)
    max_end_km: Optional[float] = Field(default=None, ge=0)
    max_total_km: Optional[float] = Field(default=None, ge=0)


class BuildResp(BaseModel):
    slot: int
    total_score: int
    matches: List[MatchItem]


# ------------------------------ DB-facing endpoints ------------------------------

@router.get("/requests-open", response_model=List[MarketRequest])
def requests_open(db: Session = Depends(get_db)) -> List[MarketRequest]:
    rows = (
        db.query(DbRequest)
        .filter(DbRequest.status == "open")
        .order_by(DbRequest.created_at.asc())
        .limit(1000)
        .all()
    )
    out: List[MarketRequest] = []
    for r in rows:
        # timestamps → ms; if tz-naive in DB, treat as UTC
        ws = int(r.window_start.replace(tzinfo=r.window_start.tzinfo or timezone.utc).timestamp() * 1000) if getattr(r, "window_start", None) else 0
        we = int(r.window_end.replace(tzinfo=r.window_end.tzinfo or timezone.utc).timestamp() * 1000) if getattr(r, "window_end", None) else 0
        out.append(MarketRequest(
            uuid_16=uuid_to_16_hex(r.id),
            from_lat=int(r.from_lat or 0),
            from_lon=int(r.from_lon or 0),
            to_lat=int(r.to_lat or 0),
            to_lon=int(r.to_lon or 0),
            max_price_cents=int(round((r.max_price or 0) * 100)),
            kind=0 if r.type == "package" else 1,
            window_start=ws,
            window_end=we,
        ))
    return out


def compute_types_mask(types) -> int:
    """
    Convert offer.types (e.g. ['package', 'passenger']) into a bitmask:
      bit 0 (1) → supports 'package'
      bit 1 (2) → supports 'passenger'
      both      → 3
    If types is None or empty, mask will be 0 (no supported types),
    which effectively prevents matching – safer than over-matching.
    """
    if types is None:
        types_list = []
    elif isinstance(types, str):
        types_list = [types]
    else:
        try:
            types_list = list(types)
        except TypeError:
            types_list = [types]

    mask = 0
    for t in types_list:
        if t == "package":
            mask |= 1
        elif t == "passenger":
            mask |= 2
    return mask


def _offers_active_impl(db: Session) -> List[MarketOffer]:
    rows = (
        db.query(CourierOffer)
        .filter(CourierOffer.status == "active")
        .order_by(CourierOffer.created_at.asc())
        .limit(1000)
        .all()
    )
    out: List[MarketOffer] = []
    for o in rows:
        tm = compute_types_mask(getattr(o, "types", None))
        log.debug(
            "offers_active: offer %s types=%r -> types_mask=%s",
            getattr(o, "id", None),
            getattr(o, "types", None),
            tm,
        )
        out.append(MarketOffer(
            uuid_16=uuid_to_16_hex(o.id),
            min_price_cents=int(round((o.min_price or 0) * 100)),
            from_lat=int(o.from_lat or 0),
            from_lon=int(o.from_lon or 0),
            to_lat=int(o.to_lat or 0),
            to_lon=int(o.to_lon or 0),
            window_start=int(o.window_start.timestamp() * 1000) if o.window_start else 0,
            window_end=int(o.window_end.timestamp() * 1000) if o.window_end else 0,
            types_mask=tm,
        ))
    return out


@router.get("/offers-active", response_model=List[MarketOffer])
def offers_active(db: Session = Depends(get_db)) -> List[MarketOffer]:
    return _offers_active_impl(db)


@router.get("/offers-open", response_model=List[MarketOffer])
def offers_open_compat(db: Session = Depends(get_db)) -> List[MarketOffer]:
    return _offers_active_impl(db)


# ------------------------------ Internal DB apply helper ------------------------------

def _apply_matches_to_db(matches: List[MatchItem], db: Session) -> dict:
    """
    Shared logic to materialize matches into DB:
    - Create assignments
    - Update requests.status='assigned'
    - Update courier_offers.status='assigned'

    NOTE:
    On-chain escrow creation is now handled by `/escrows/initiate` when the
    payer clicks "continue to payment" in the app. This helper ONLY updates
    the relational DB and does NOT call the Escrow pallet anymore.
    """
    print("[ESCROW DEBUG] entered _apply_matches_to_db, matches count =", len(matches))

    if not matches:
        print("[ESCROW DEBUG] no matches → nothing to apply")
        return {
            "ok": True,
            "created": 0,
            "updated_requests": 0,
            "updated_offers": 0,
            "escrows_created": 0,  # kept for backward compatibility
        }

    created = 0
    upd_r = 0
    upd_o = 0

    for m in matches:
        print(
            "[ESCROW DEBUG] processing match:",
            "req=", m.request_uuid,
            "offer=", m.offer_uuid,
            "agreed_price_cents=", m.agreed_price_cents,
        )

        # Convert hex32 → UUIDs
        try:
            rq_uuid = _hex32_to_uuid(m.request_uuid)
            of_uuid = _hex32_to_uuid(m.offer_uuid)
        except Exception as e:
            print("[ESCROW DEBUG] invalid UUID in match, skipping:", repr(e))
            continue

        # Look up the (request, offer, driver_user_id) triple in DB
        sel = text("""
            SELECT
                r.id::text AS request_id,
                o.id::text AS offer_id,
                o.driver_user_id::text AS driver_user_id
            FROM requests r
            JOIN courier_offers o ON o.id = CAST(:offer_id AS uuid)
            WHERE r.id = CAST(:request_id AS uuid)
            LIMIT 1
        """)
        row = db.execute(
            sel,
            {"request_id": str(rq_uuid), "offer_id": str(of_uuid)},
        ).mappings().first()
        if not row:
            print("[ESCROW DEBUG] no (request, offer) row found for match, skipping")
            continue

        request_id = row["request_id"]
        offer_id = row["offer_id"]
        driver_user_id = row["driver_user_id"]
        print(
            "[ESCROW DEBUG] DB pair found: request_id=",
            request_id,
            "offer_id=",
            offer_id,
            "driver_user_id=",
            driver_user_id,
        )

        # Skip if an active assignment already exists for this request
        exists = db.execute(
            text("""
                SELECT 1 FROM assignments
                WHERE request_id = CAST(:rid AS uuid)
                  AND status IN ('created','picked_up','in_transit')
                LIMIT 1
            """),
            {"rid": request_id},
        ).first()
        if exists:
            print(
                "[ESCROW DEBUG] assignment already exists for request",
                request_id,
                "→ skipping",
            )
            continue

        # Insert the assignment row
        ins = text("""
            INSERT INTO assignments
              (request_id, driver_user_id, offer_id, agreed_price_cents, status, assigned_at)
            VALUES
              (
                CAST(:rid AS uuid),
                CAST(:duid AS uuid),
                CAST(:oid AS uuid),
                :agreed_price_cents,
                'created',
                NOW()
              )
            RETURNING id
        """)
        arow = db.execute(
            ins,
            {
                "rid": request_id,
                "duid": driver_user_id,
                "oid": offer_id,
                "agreed_price_cents": int(m.agreed_price_cents),
            },
        ).mappings().first()
        if arow:
            created += 1
            print("[ESCROW DEBUG] assignment created, id =", arow["id"])

        # Update request status → 'assigned'
        db.execute(
            text(
                "UPDATE requests SET status='assigned', updated_at=NOW() "
                "WHERE id = CAST(:rid AS uuid)"
            ),
            {"rid": request_id},
        )
        upd_r += 1

        # Update courier offer status → 'assigned'
        db.execute(
            text(
                "UPDATE courier_offers SET status='assigned', updated_at=NOW() "
                "WHERE id = CAST(:oid AS uuid)"
            ),
            {"oid": offer_id},
        )
        upd_o += 1

        # NOTE:
        # We deliberately DO NOT create any on-chain escrow here anymore.
        # Escrow rows (DB + chain) are created later via /escrows/initiate,
        # when the payer explicitly clicks the payment button in the app.

    db.commit()
    print(
        "[ESCROW DEBUG] done apply_matches, created assignments =",
        created,
        "updated_requests =",
        upd_r,
        "updated_offers =",
        upd_o,
        "escrows_created = 0 (handled via /escrows/initiate now)",
    )

    return {
        "ok": True,
        "created": created,
        "updated_requests": upd_r,
        "updated_offers": upd_o,
        "escrows_created": 0,  # kept for backward compatibility
    }


# ------------------------------ Chain calls ------------------------------

def _submit_with_wait(substrate, extrinsic, *, label: str):
    """
    Helper to submit extrinsic and wait according to env flags.
    Waits for finalization if POBA_WAIT_FINALIZATION=1, otherwise for inclusion.
    Does NOT use unsupported 'timeout' argument (compatible with older substrate-interface).
    Falls back gracefully from finalization→inclusion and retries JSONDecodeError once.
    """
    wait_final = _wait_for_finalization()

    if wait_final:
        try:
            return substrate.submit_extrinsic(
                extrinsic,
                wait_for_finalization=True
            )
        except (JSONDecodeError, SubstrateRequestException) as e:
            log.warning("%s: finalization wait failed (%s), falling back to inclusion", label, e)

    # Fallback: inclusion (default behavior)
    try:
        return substrate.submit_extrinsic(
            extrinsic,
            wait_for_inclusion=True
        )
    except JSONDecodeError as e:
        # Known hiccup: retry once; if fails again, send without wait
        log.warning("%s inclusion wait JSONDecodeError: %s; retrying once", label, e)
        time.sleep(0.2)
        try:
            return substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        except JSONDecodeError as e2:
            log.warning("%s: second inclusion wait failed (%s); sending without wait", label, e2)
            return substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)


@router.post("/submit-proposal")
def submit_proposal(body: SubmitProposalBody, request: Request):
    """
    Submit (or improve) the best proposal for a slot to the PoBA pallet.
    Now includes retry with increasing `tip` to overcome 1014 "Priority is too low".
    Also supports waiting for FINALIZATION via POBA_WAIT_FINALIZATION=1.

    API semantics:
      - Domain "no matches" is NOT treated as an HTTP error:
        we return ok=false, submitted=false, reason="no_matches" with HTTP 200.
      - Network / RPC / dispatch problems ARE errors (4xx/5xx).

    proposer_id (optional, via query param):
      - /poba/submit-proposal?proposer_id=alice
      - /poba/submit-proposal?proposer_id=bob
    Used to pick a per-proposer signer on chain.
    """
    proposer_id = request.query_params.get("proposer_id") or None

    # Soft guard: no matches means "nothing to submit", not an error.
    if not body.matches:
        total_score = int(body.total_score or 0)
        return {
            "ok": False,
            "submitted": False,
            "reason": "no_matches",
            "slot": body.slot,
            "total_score": total_score,
            "matches": [],
        }

    substrate = get_substrate()
    signer = get_signer(proposer_id=proposer_id)

    # Quick health probe (helps with nicer error if WS is down)
    try:
        health = substrate.rpc_request("system_health", [])
        log.info("system_health: %s", health)
    except SubstrateRequestException as e:
        log.exception("RPC system_health failed: %s", e)
        raise HTTPException(status_code=502, detail={
            "code": "rpc_system_health_failed",
            "error": str(e),
            "hint": "Check WS URL and node availability",
        })

    matches_param_name = _param_matches()
    # If client didn't send a score, fall back to 0 (do not fabricate any other value).
    total_score = int(body.total_score or 0)

    try:
        # Convert match items → SCALE tuple-vec
        match_tuples: List[List[int] | Tuple[List[int], List[int], int, int]] = []
        for m in body.matches:
            match_tuples.append([
                hex16_to_u8_array_16(m.request_uuid),
                hex16_to_u8_array_16(m.offer_uuid),
                int(m.agreed_price_cents),
                int(m.partial_score),
            ])

        call = substrate.compose_call(
            call_module=_pallet_name(),
            call_function=_call_submit(),
            call_params={
                "slot": int(body.slot),
                "total_score": total_score,
                matches_param_name: match_tuples,
            },
        )

        # ---- priority-aware retry with increasing tip ----
        MAX_ATTEMPTS = int(os.getenv("POBA_TX_MAX_ATTEMPTS", "3"))
        BASE_TIP = int(os.getenv("POBA_TX_TIP_BASE", "0"))
        TIP_STEP = int(os.getenv("POBA_TX_TIP_STEP", "1000"))
        BACKOFF_MS = int(os.getenv("POBA_TX_BACKOFF_MS", "150"))

        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            tip = BASE_TIP + (attempt - 1) * TIP_STEP
            extrinsic = substrate.create_signed_extrinsic(call=call, keypair=signer, tip=tip)

            try:
                receipt = _submit_with_wait(substrate, extrinsic, label="submit_proposal")
                ok = getattr(receipt, "is_success", None)
                log.info(
                    "submit_proposal included/finalized: ok=%s hash=%s tip=%s proposer_id=%s",
                    ok,
                    receipt.extrinsic_hash,
                    tip,
                    proposer_id,
                )
                for ev in getattr(receipt, "triggered_events", []) or []:
                    try:
                        mod = ev.value["event"]["module"]
                        name = ev.value["event"]["event"]
                        log.info("submit_proposal event: %s::%s", mod, name)
                    except Exception:
                        pass

                if ok is False:
                    raise HTTPException(status_code=502, detail={
                        "code": "dispatch_failed",
                        "hint": "Check pallet event / error data; ensure types and param names match runtime",
                        "receipt": str(getattr(receipt, "error_message", "")),
                    })

                return {"ok": True, "submitted": True, "hash": receipt.extrinsic_hash}

            except SubstrateRequestException as e:
                # Handle 1014 "Priority is too low"
                msg = str(getattr(e, "args", [""])[0]) or str(e)
                is_priority_low = ("Priority is too low" in msg) or ("'code': 1014" in msg) or ('"code": 1014' in msg)
                if is_priority_low and attempt < MAX_ATTEMPTS:
                    log.warning(
                        "submit_proposal retry due to low priority (attempt %s/%s, tip=%s): %s",
                        attempt,
                        MAX_ATTEMPTS,
                        tip,
                        msg,
                    )
                    time.sleep((BACKOFF_MS * attempt) / 1000.0)
                    last_err = e
                    continue
                log.exception("submit_proposal RPC failed: %s", e)
                raise HTTPException(status_code=502, detail={
                    "code": "rpc_submit_failed",
                    "error": str(e),
                    "hint": "Verify pallet/call/param names and signer funds",
                })

        raise HTTPException(status_code=502, detail={
            "code": "tx_priority_retries_exhausted",
            "error": str(last_err) if last_err else "unknown",
        })

    except HTTPException:
        raise
    except Exception as e:
        log.exception("submit_proposal failed: %s", e)
        raise HTTPException(status_code=500, detail={
            "code": "submit_proposal_failed",
            "error": str(e),
        })


def _finalize_slot_impl(body: FinalizeBody, proposer_id: Optional[str] = None) -> dict:
    """
    Internal helper that performs finalize-slot on chain.

    IMPORTANT:
      - This no longer auto-applies matches into the DB.
      - Instead, a separate background listener watches LastFinalizedSlot and
        applies FinalizedProposal(slot) there.
    """
    substrate = get_substrate()
    signer = get_signer(proposer_id=proposer_id)

    # Guard: don't finalize a slot if there is no BestProposal with matches>0
    try:
        bp = substrate.query(_pallet_name(), "BestProposal", [int(body.slot)]).value
    except Exception as e:
        log.warning("finalize_slot: failed to query BestProposal for slot %s: %s", body.slot, e)
        bp = None

    if not bp or not (bp.get("matches") or []):
        return {"ok": False, "skipped": True, "reason": "no_best_proposal_for_slot", "slot": body.slot}

    try:
        call = substrate.compose_call(
            call_module=_pallet_name(),
            call_function=_call_finalize(),
            call_params={"slot": int(body.slot)},
        )

        # ---- priority-aware retry with increasing tip ----
        MAX_ATTEMPTS = int(os.getenv("POBA_TX_MAX_ATTEMPTS", "3"))
        BASE_TIP = int(os.getenv("POBA_TX_TIP_BASE", "0"))
        TIP_STEP = int(os.getenv("POBA_TX_TIP_STEP", "1000"))
        BACKOFF_MS = int(os.getenv("POBA_TX_BACKOFF_MS", "150"))

        receipt = None
        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            tip = BASE_TIP + (attempt - 1) * TIP_STEP
            extrinsic = substrate.create_signed_extrinsic(call=call, keypair=signer, tip=tip)
            try:
                receipt = _submit_with_wait(substrate, extrinsic, label="finalize_slot")
                break
            except SubstrateRequestException as e:
                msg = str(getattr(e, "args", [""])[0]) or str(e)
                is_priority_low = ("Priority is too low" in msg) or ("'code': 1014" in msg) or ('"code": 1014' in msg)
                if is_priority_low and attempt < MAX_ATTEMPTS:
                    log.warning(
                        "finalize_slot retry due to low priority (attempt %s/%s, tip=%s): %s",
                        attempt,
                        MAX_ATTEMPTS,
                        tip,
                        msg,
                    )
                    time.sleep((BACKOFF_MS * attempt) / 1000.0)
                    last_err = e
                    continue
                raise

        if receipt is None:
            raise HTTPException(status_code=502, detail={
                "code": "rpc_finalize_failed",
                "error": str(last_err) if last_err else "unknown",
            })

        ok = getattr(receipt, "is_success", None)
        log.info(
            "finalize_slot included/finalized: ok=%s hash=%s proposer_id=%s",
            ok,
            receipt.extrinsic_hash,
            proposer_id,
        )
        for ev in getattr(receipt, "triggered_events", []) or []:
            try:
                mod = ev.value["event"]["module"]
                name = ev.value["event"]["event"]
                log.info("finalize_slot event: %s::%s", mod, name)
            except Exception:
                pass

        if ok is False:
            raise HTTPException(status_code=502, detail={
                "code": "dispatch_failed",
                "hint": "Check pallet finalize error",
                "receipt": str(getattr(receipt, "error_message", "")),
            })

        # No DB apply here – handled by background listener.
        return {"ok": True, "hash": receipt.extrinsic_hash}
    except SubstrateRequestException as e:
        log.exception("finalize_slot RPC failed: %s", e)
        raise HTTPException(status_code=502, detail={
            "code": "rpc_finalize_failed",
            "error": str(e),
        })
    except HTTPException:
        raise
    except Exception as e:
        log.exception("finalize_slot failed: %s", e)
        raise HTTPException(status_code=500, detail={
            "code": "finalize_slot_failed",
            "error": str(e),
        })


@router.post("/finalize-slot")
def finalize_slot(body: FinalizeBody, request: Request):
    """
    API wrapper for /finalize-slot that extracts proposer_id from the query
    and forwards it to the internal implementation.
    """
    log.warning("### FINALIZE_SLOT CALLED from backend, slot=%s ###", body.slot)

    proposer_id = request.query_params.get("proposer_id") or None
    return _finalize_slot_impl(body, proposer_id=proposer_id)


# ------------------------------ Proposal builder (IDA*) ------------------------------

@router.post("/build-proposal", response_model=BuildResp)
def build_proposal(body: BuildBody, request: Request) -> BuildResp:
    """
    Compute an assignment with IDA* for BidDrop.

    DB mapping (for clarity):
      - Requests come from `requests` table:
          * id, owner_user_id, type (passenger/package)
          * from_lat, from_lon, to_lat, to_lon
          * window_start, window_end (ms since epoch, after conversion)
          * max_price (NUMERIC) or max_price_cents (int) in models
      - Offers come from `courier_offers` table:
          * id, driver_user_id
          * from_lat, from_lon, to_lat, to_lon
          * window_start, window_end (ms since epoch, after conversion)
          * min_price (NUMERIC) or min_price_cents (int) in models
          * types (array: ['package'] or ['package', 'passenger'])

    Constraints (per-pair feasibility):
      - Type:  request.type must be in offer.types (if both present)
      - Price: offer.min_price_cents <= request.max_price_cents (0 means "no max")
      - Time:  request window must overlap offer window (configurable, see env below)
      - Distance caps (optional): max_start_km / max_end_km / max_total_km
      - Each offer is used at most once
      - Requests are considered in given order; we may SKIP a request with a heavy penalty.

    Cost model:
      penalty = ALPHA * (d_start + d_end) + BETA * agreed_price_cents
      (lower is better)

    Score model (for chain, positive and additive):
      score = max(0, BASE - penalty)

    proposer_id (optional, via query param) is currently only logged for tracing.
    """
    from decimal import Decimal
    from typing import Tuple as Tup, Iterable as _Iterable, Optional as _Optional

    proposer_id = request.query_params.get("proposer_id") or None
    if proposer_id:
        log.info("build_proposal: slot=%s from proposer_id=%s", body.slot, proposer_id)

    R = body.requests
    O = body.offers
    n = len(R)
    m = len(O)

    # ---------------- Scoring parameters (tunable) ----------------
    BASE = int(os.getenv("POBA_BASE_SCORE", "1000000"))    # keep scores positive
    ALPHA = float(os.getenv("POBA_ALPHA_PER_KM", "1000"))  # penalty per km
    BETA = float(os.getenv("POBA_BETA_PER_CENT", "1"))     # penalty per cent

    # Heavy penalty for skipping a request (so we prefer matching when possible)
    SKIP_COST = int(os.getenv("POBA_SKIP_COST", "100000000"))  # default 1e8

    # Optional pairwise distance caps (via request, or ENV fallback)
    max_start_km = body.max_start_km if body.max_start_km is not None else (float(os.getenv("POBA_MAX_START_KM", "0")) or None)
    max_end_km = body.max_end_km if body.max_end_km is not None else (float(os.getenv("POBA_MAX_END_KM", "0")) or None)
    max_total_km = body.max_total_km if body.max_total_km is not None else (float(os.getenv("POBA_MAX_TOTAL_KM", "0")) or None)

    # ---------------- Time-overlap requirements ----------------
    # All values are interpreted in milliseconds (ms) since epoch (UTC)
    REQUIRE_TIME_OVERLAP = os.getenv("POBA_REQUIRE_TIME_OVERLAP", "1").lower() not in {"0", "false", "no", ""}
    MIN_OVERLAP_MS = int(float(os.getenv("POBA_MIN_OVERLAP_SEC", "0")) * 1000)
    # Optional slack: allow an offer to start a bit earlier / end a bit later
    EARLY_SLACK_MS = int(float(os.getenv("POBA_EARLY_SLACK_SEC", "0")) * 1000)
    LATE_SLACK_MS = int(float(os.getenv("POBA_LATE_SLACK_SEC", "0")) * 1000)

    def intervals_overlap_ms(
        a_start: int,
        a_end: int,
        b_start: int,
        b_end: int,
        min_olap: int = 0,
        early_slack: int = 0,
        late_slack: int = 0,
    ) -> bool:
        """
        Check if [a_start, a_end] and [b_start, b_end] overlap at least `min_olap` ms,
        allowing slack on the 'b' interval: b_start -= early_slack, b_end += late_slack.
        All times are ms since epoch (UTC).

        If any bound is missing/zero and REQUIRE_TIME_OVERLAP is True, we treat it as
        "no guaranteed overlap" and return False (i.e., drop the pair).
        """
        if not (a_start and a_end and b_start and b_end):
            return not REQUIRE_TIME_OVERLAP
        b_s = b_start - early_slack
        b_e = b_end + late_slack
        overlap = min(a_end, b_e) - max(a_start, b_s)
        return overlap >= max(0, min_olap)

    # ---------------- Price helpers (match DB: max_price, min_price) ----------------

    def _get_attr(obj, *names, default=None):
        """Return first existing attribute from names, or default."""
        for name in names:
            if hasattr(obj, name):
                return getattr(obj, name)
        return default

    def _to_cents(value) -> int:
        """
        Normalize value (possibly NUMERIC, Decimal, float, int) into cents.
        If it's already an int (e.g. *_cents), keep as-is.
        If None → 0.
        """
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, Decimal):
            return int(value * 100)
        if isinstance(value, float):
            return int(round(value * 100))
        try:
            # string or other numeric-like
            return int(value)
        except Exception:
            return 0

    # ---------------- Debug counters to understand why pairs are dropped ----------------
    debug_counts = {
        "total_pairs": 0,
        "filtered_by_type": 0,
        "filtered_by_price": 0,
        "filtered_by_time": 0,
        "filtered_by_distance": 0,
        "feasible_pairs": 0,
    }

    # ---------------- Precompute pair cost/score ----------------
    INF = 10**12  # sufficiently large
    cost = [[INF] * m for _ in range(n)]
    partial_score = [[0] * m for _ in range(n)]
    price_agreed = [[0] * m for _ in range(n)]  # agreed price in cents per (request, offer)

    def haversine_km(lat1_e6: int, lon1_e6: int, lat2_e6: int, lon2_e6: int) -> float:
        """Approximate distance in km between two geo points given in micro-degrees."""
        to_rad = lambda x: (x / 1_000_000.0) * math.pi / 180.0
        lat1, lon1, lat2, lon2 = map(to_rad, [lat1_e6, lon1_e6, lat2_e6, lon2_e6])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = (math.sin(dlat / 2) ** 2) + math.cos(lat1) * math.cos(lat2) * (math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(a**0.5, (1 - a)**0.5)
        return 6371.0 * c

    for i, r in enumerate(R):
        for j, o in enumerate(O):
            debug_counts["total_pairs"] += 1

            # 0) Type feasibility (if both sides carry type information)
            r_type = getattr(r, "type", None)
            o_types = getattr(o, "types", None)
            if r_type is not None and o_types is not None:
                # courier_offers.types is expected to be a list/tuple like ['package', 'passenger']
                try:
                    if r_type not in list(o_types):
                        debug_counts["filtered_by_type"] += 1
                        continue
                except TypeError:
                    debug_counts["filtered_by_type"] += 1
                    continue

            # 1) Price feasibility
            #    DB: requests.max_price (NUMERIC)   → r.max_price or r.max_price_cents
            #        courier_offers.min_price      → o.min_price or o.min_price_cents
            req_max_raw = _get_attr(r, "max_price_cents", "max_price", default=0)
            off_min_raw = _get_attr(o, "min_price_cents", "min_price", default=0)
            req_max_cents = _to_cents(req_max_raw)
            off_min_cents = _to_cents(off_min_raw)

            # 0 means "no max"
            if req_max_cents and off_min_cents > req_max_cents:
                debug_counts["filtered_by_price"] += 1
                continue

            # 2) Time-window feasibility
            if REQUIRE_TIME_OVERLAP:
                r_ws = getattr(r, "window_start", None)
                r_we = getattr(r, "window_end", None)
                o_ws = getattr(o, "window_start", None)
                o_we = getattr(o, "window_end", None)

                if not intervals_overlap_ms(
                    r_ws, r_we,
                    o_ws, o_we,
                    min_olap=MIN_OVERLAP_MS,
                    early_slack=EARLY_SLACK_MS,
                    late_slack=LATE_SLACK_MS,
                ):
                    debug_counts["filtered_by_time"] += 1
                    continue

            # 3) Distance feasibility
            r_fl = getattr(r, "from_lat", None)
            r_fn = getattr(r, "from_lon", None)
            r_tl = getattr(r, "to_lat", None)
            r_tn = getattr(r, "to_lon", None)
            o_fl = getattr(o, "from_lat", None)
            o_fn = getattr(o, "from_lon", None)
            o_tl = getattr(o, "to_lat", None)
            o_tn = getattr(o, "to_lon", None)

            # Lat/lon in DB may be NULL. If coords are missing and caps are set, drop the pair.
            if None in (r_fl, r_fn, r_tl, r_tn, o_fl, o_fn, o_tl, o_tn):
                if any(x is not None for x in (max_start_km, max_end_km, max_total_km)):
                    debug_counts["filtered_by_distance"] += 1
                    continue
                # no caps → treat distance as 0
                d_start = 0.0
                d_end = 0.0
            else:
                d_start = haversine_km(r_fl, r_fn, o_fl, o_fn)
                d_end = haversine_km(r_tl, r_tn, o_tl, o_tn)

            d_total = d_start + d_end

            if max_start_km is not None and d_start > max_start_km:
                debug_counts["filtered_by_distance"] += 1
                continue
            if max_end_km is not None and d_end > max_end_km:
                debug_counts["filtered_by_distance"] += 1
                continue
            if max_total_km is not None and d_total > max_total_km:
                debug_counts["filtered_by_distance"] += 1
                continue

            # 4) Agreed price policy:
            #    If request has a max_price_cents > 0:
            #       agreed_price = midpoint between min_price and max_price
            #    Else:
            #       agreed_price = offer.min_price
            if req_max_cents > 0:
                agreed = (off_min_cents + req_max_cents) // 2
            else:
                agreed = off_min_cents

            p_cents = max(1, int(agreed))

            # 5) Scoring
            penalty = int(ALPHA * d_total + BETA * p_cents)  # minimize penalty
            sc = max(0, BASE - penalty)                      # positive score (maximize on-chain)

            partial_score[i][j] = int(sc)
            price_agreed[i][j] = p_cents
            cost[i][j] = penalty
            debug_counts["feasible_pairs"] += 1

    # ---------------- IDA* state space ----------------

    def is_goal(state: Tup[int, int, int]) -> bool:
        i, used_mask, g = state
        return i == n

    def h(state: Tup[int, int, int]) -> float:
        # Admissible lower bound: 0 (safe).
        return 0.0

    def expand(state: Tup[int, int, int]) -> _Iterable[Tup[Tup[int, int, int], float]]:
        i, used_mask, g = state
        if i >= n:
            return []
        succ = []

        # Penalized "skip request i"
        succ.append(((i + 1, used_mask, g + SKIP_COST), SKIP_COST))

        # Try to match request i with any unused feasible offer j
        for j in range(m):
            if (used_mask >> j) & 1:
                continue
            c_ij = cost[i][j]
            if c_ij >= INF:
                continue
            next_state = (i + 1, used_mask | (1 << j), g + c_ij)
            succ.append((next_state, c_ij))
        return succ

    def key(state: Tup[int, int, int]):
        return (state[0], state[1])

    start = (0, 0, 0)
    goal, best_cost = ida_star(start=start, h=h, expand=expand, is_goal=is_goal, key=key)

    matches: List[MatchItem] = []
    total_score = 0

    if goal is None:
        log.info(
            "build_proposal: no feasible assignment (slot=%s) debug=%s",
            body.slot,
            debug_counts,
        )
        return BuildResp(slot=body.slot, total_score=0, matches=[])

    # ---------------- Reconstruct one optimal plan ----------------
    i, used_mask, acc = 0, 0, 0
    while i < n:
        chosen_j: _Optional[int] = None

        # Prefer a real match if possible (and still optimal)
        for j in range(m):
            if (used_mask >> j) & 1:
                continue
            c_ij = cost[i][j]
            if c_ij >= INF:
                continue
            if acc + c_ij <= best_cost:
                chosen_j = j
                break

        if chosen_j is not None:
            matches.append(MatchItem(
                request_uuid=R[i].uuid_16,
                offer_uuid=O[chosen_j].uuid_16,
                agreed_price_cents=int(price_agreed[i][chosen_j]),
                partial_score=int(partial_score[i][chosen_j]),
            ))
            total_score += int(partial_score[i][chosen_j])
            used_mask |= (1 << chosen_j)
            acc += int(cost[i][chosen_j])
            i += 1
            continue

        # Otherwise we must have skipped this request in the optimal path
        if acc + SKIP_COST <= best_cost:
            acc += SKIP_COST
            i += 1
            continue

        break

    log.info(
        "build_proposal: slot=%s total_score=%s matches=%s "
        "(skip_cost=%s, require_time_overlap=%s, min_overlap_ms=%s, "
        "early_slack_ms=%s, late_slack_ms=%s, proposer_id=%s, debug=%s)",
        body.slot, total_score, len(matches), SKIP_COST,
        REQUIRE_TIME_OVERLAP, MIN_OVERLAP_MS, EARLY_SLACK_MS, LATE_SLACK_MS,
        proposer_id, debug_counts,
    )
    return BuildResp(slot=body.slot, total_score=total_score, matches=matches)


# ------------------------------ Diagnostics ------------------------------

@router.get("/chain-health")
def chain_health():
    """Quick RPC checks: chain name, health, runtime version, best header."""
    sub = get_substrate()
    try:
        chain = sub.rpc_request("system_chain", [])
        health = sub.rpc_request("system_health", [])
        rt = sub.rpc_request("state_getRuntimeVersion", [])
        head = sub.rpc_request("chain_getHeader", [])
        return {
            "ws_url": _ws_url(),
            "chain": chain,
            "health": health,
            "runtime": rt,
            "best_header": head,
        }
    except SubstrateRequestException as e:
        raise HTTPException(status_code=502, detail={
            "code": "rpc_failed",
            "error": str(e),
        })


@router.get("/debug-config")
def debug_config():
    return {
        "ws_url": _ws_url(),
        "type_registry_preset": _type_registry_preset(),
        "pallet": _pallet_name(),
        "call_submit": _call_submit(),
        "call_finalize": _call_finalize(),
        "param_matches": _param_matches(),
        "signer_uri_present": bool(os.getenv("SUBSTRATE_SIGNER_URI")),
        "signer_mnemonic_present": bool(os.getenv("SUBSTRATE_SIGNER_MNEMONIC")),
        "signer_source": "URI" if os.getenv("SUBSTRATE_SIGNER_URI") else (
            "MNEMONIC" if os.getenv("SUBSTRATE_SIGNER_MNEMONIC") else "NONE"
        ),
        "wait_for_finalization": _wait_for_finalization(),
        "finalization_timeout_sec": _finalization_timeout_sec(),
        "auto_apply": os.getenv("BID_AUTO_APPLY", "0"),

        # 🔍 Escrow debug (now only for separate /escrows routes)
        "escrow_enable": os.getenv("ESCROW_ENABLE", "0"),
        "escrow_pallet": _escrow_pallet_name(),
        "escrow_call_create": _escrow_call_create(),
    }


@router.get("/whoami")
def whoami():
    """
    Return the signer source and, if valid, the SS58 address and free balance.
    Helps diagnose invalid mnemonic/SURI and insufficient funds.
    """
    src = "URI" if os.getenv("SUBSTRATE_SIGNER_URI") else ("MNEMONIC" if os.getenv("SUBSTRATE_SIGNER_MNEMONIC") else "NONE")
    out = {"signer_source": src}
    try:
        kp = get_signer()  # global default signer
    except HTTPException as e:
        out["error"] = e.detail
        return out

    out["ss58_address"] = kp.ss58_address
    try:
        sub = get_substrate()
        # System.Account → data.free
        acc = sub.query("System", "Account", [kp.ss58_address])
        free = int(acc.value["data"]["free"])
        out["free"] = free
        out["free_units_hint"] = "value is in the chain's base units"
    except Exception as e:
        out["balance_error"] = str(e)
    return out


# ------------------------------ Apply endpoints ------------------------------

@router.post("/apply-proposal")
def apply_proposal(
    payload: SubmitProposalBody = Body(...),
    db: Session = Depends(get_db),
):
    """
    Materialize a (built or finalized) proposal into the DB:
    - Create assignments(request_id, driver_user_id, offer_id, agreed_price_cents, status, assigned_at)
    - Update requests.status='assigned'
    - Update courier_offers.status='assigned'

    NOTE:
    This does NOT create any on-chain escrow. Escrows are now created by
    /escrows/initiate when the payer clicks the payment button.
    """
    return _apply_matches_to_db(payload.matches or [], db)


@router.post("/finalize-and-apply")
def finalize_and_apply(
    payload: SubmitProposalBody = Body(...),
):
    """
    Convenience endpoint (manual use):
    1) finalize-slot on chain (waits for finalization if POBA_WAIT_FINALIZATION=1)
    2) apply the same matches to DB immediately

    NOTE:
    This only touches the DB. On-chain escrows are created later via /escrows/initiate.
    The "normal" flow כעת אמור להיות דרך המאזין שמגיב ל־LastFinalizedSlot.
    """
    # 1) finalize on chain (no specific proposer_id, use default signer)
    fin = _finalize_slot_impl(FinalizeBody(slot=payload.slot), proposer_id=None)
    if not fin or not fin.get("ok"):
        return {"ok": False, "where": "finalize", "resp": fin}

    # 2) apply into DB
    db = SessionLocal()
    try:
        applied = _apply_matches_to_db(payload.matches or [], db)
    finally:
        db.close()

    return {"ok": True, "finalize": fin, "apply": applied}


# ------------------------------ SlotFinalized listener ------------------------------

def _load_matches_from_finalized(substrate: SubstrateInterface, slot: int) -> List[MatchItem]:
    """
    Load FinalizedProposal(slot) from chain and convert to MatchItem list.
    Falls back to BestProposal(slot) if FinalizedProposal is None/empty.

    Supports both:
      - tuple-style: (req_u8[16], off_u8[16], price_cents, partial_score)
      - dict-style:  {
                       requestUuid / request_uuid: [u8;16] or "0x..",
                       offerUuid   / offer_uuid:   [u8;16] or "0x..",
                       agreedPriceCents / agreed_price_cents: int,
                       partialScore      / partial_score:      int
                     }
    """
    pallet = _pallet_name()
    fp = None
    try:
        fp = substrate.query(pallet, "FinalizedProposal", [int(slot)]).value
    except Exception as e:
        log.warning("slot_listener: failed to query FinalizedProposal(%s): %s", slot, e)
        fp = None

    if not fp:
        # Fallback: try BestProposal (depends on how pallet is implemented)
        try:
            fp = substrate.query(pallet, "BestProposal", [int(slot)]).value
            log.info("slot_listener: using BestProposal(%s) as fallback", slot)
        except Exception as e:
            log.warning("slot_listener: failed to query BestProposal(%s): %s", slot, e)
            fp = None

    items = (fp or {}).get("matches") or []
    matches: List[MatchItem] = []

    if not items:
        log.info("slot_listener: slot=%s has no matches in finalized proposal", slot)
        return matches

    def _to_hex_from_u8(x) -> str:
        """Normalize various forms (list[int], bytes, '0x..') into plain 32-hex."""
        if x is None:
            return ""
        # Already hex string
        if isinstance(x, str):
            s = x.lower()
            if s.startswith("0x"):
                s = s[2:]
            return s
        # bytes / bytearray
        if isinstance(x, (bytes, bytearray)):
            return x.hex()
        # list/tuple of ints
        try:
            return bytes(x).hex()
        except Exception:
            # last resort
            return "".join(f"{int(b):02x}" for b in x)

    for it in items:
        # ---- dict-style (what את רואה ב-Polkadot.js) ----
        if isinstance(it, dict):
            rq_raw = (
                it.get("requestUuid")
                or it.get("request_uuid")
            )
            of_raw = (
                it.get("offerUuid")
                or it.get("offer_uuid")
            )
            price_raw = (
                it.get("agreedPriceCents")
                or it.get("agreed_price_cents")
            )
            score_raw = (
                it.get("partialScore")
                or it.get("partial_score")
            )

            if rq_raw is None or of_raw is None:
                log.warning("slot_listener: match item missing uuids: %r", it)
                continue

            rq_hex = _to_hex_from_u8(rq_raw)
            of_hex = _to_hex_from_u8(of_raw)
            price_cents = int(price_raw) if price_raw is not None else 0
            partial = int(score_raw) if score_raw is not None else 0

        else:
            # ---- tuple-style compatibility ----
            try:
                rq_hex = _to_hex_from_u8(it[0])
                of_hex = _to_hex_from_u8(it[1])
                price_cents = int(it[2])
                partial = int(it[3])
            except Exception as e:
                log.warning("slot_listener: unexpected match item format (%r): %r", e, it)
                continue

        matches.append(MatchItem(
            request_uuid=rq_hex,
            offer_uuid=of_hex,
            agreed_price_cents=price_cents,
            partial_score=partial,
        ))

    return matches


def _slot_listener_loop():
    """
    Background loop:
      - Connects to Substrate
      - Periodically polls PoBA::LastFinalizedSlot
      - When the value increases, loads *that slot only* and applies matches into DB.

    """
    poll_interval = _slot_poll_interval_sec()
    pallet = _pallet_name()

    log.warning("PoBA slot listener starting (poll interval = %ss)", poll_interval)

    last_seen_slot: Optional[int] = None

    while True:
        try:
            substrate = get_substrate()
            log.info("PoBA slot listener connected to %s", _ws_url())

            while True:
                try:
                    val = substrate.query(pallet, "LastFinalizedSlot", []).value
                    if val is None:
                        # No finalized slots yet
                        time.sleep(poll_interval)
                        continue

                    current_slot = int(val)

                    if last_seen_slot is None:
                        # First run: just remember what the chain says now,
                        last_seen_slot = current_slot
                        log.info(
                            "slot_listener: initial LastFinalizedSlot=%s (no retro-apply)",
                            current_slot,
                        )
                    elif current_slot > last_seen_slot:
                        slot = current_slot
                        log.warning("slot_listener: detected new finalized slot=%s", slot)
                        matches = _load_matches_from_finalized(substrate, slot)
                        if matches:
                            db = SessionLocal()
                            try:
                                apply_result = _apply_matches_to_db(matches, db)
                                log.warning(
                                    "slot_listener: applied slot=%s result=%s",
                                    slot,
                                    apply_result,
                                )
                            finally:
                                db.close()
                        else:
                            log.info("slot_listener: slot=%s had no matches to apply", slot)

                        last_seen_slot = current_slot

                    time.sleep(poll_interval)
                except Exception as inner:
                    log.warning("slot_listener inner error: %s", inner)
                    time.sleep(poll_interval)

        except Exception as outer:
            log.error("slot_listener outer error (reconnecting in 5s): %s", outer)
            time.sleep(5)


# ------------------------------ SlotFinalized listener starter ------------------------------

_listener_started: bool = False


def install_poba_slot_listener(app: FastAPI):
    """
    Start the PoBA slot listener thread.

    NOTE:
    We *don't* rely on FastAPI startup events here, because the app uses a
    custom `lifespan` context in main.py. Instead, we start the daemon thread
    immediately the first time this function is called.

    Usage in main.py:
        from .routes_poba import router as poba_router, install_poba_slot_listener

        app = FastAPI(lifespan=lifespan)
        app.include_router(poba_router)
        install_poba_slot_listener(app)
    """
    global _listener_started
    if _listener_started:
        log.info("PoBA slot listener already started (skipping)")
        return

    t = Thread(target=_slot_listener_loop, daemon=True)
    t.start()
    _listener_started = True
    log.warning("PoBA slot listener thread started (eager start)")
