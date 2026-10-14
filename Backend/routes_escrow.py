# Backend/routes_escrow.py
# Escrow lifecycle endpoints.
# IMPORTANT:
# - /escrows/initiate is called ONLY when the user clicks "pay".
# - This endpoint:
#     1) Verifies assignment + permissions in the DB.
#     2) Creates (or reuses) an Escrow row in the DB.
#     3) Calls the on-chain `Escrow::create_escrow` extrinsic with:
#        (request_uuid, offer_uuid, driver, payer, amount).
#   -> This emits an `EscrowCreated` event on-chain.
#
# Additional flows:
# - /escrows/confirm-delivered:
#     * Called by the sender/rider (request owner) to confirm delivery.
#     * Updates escrow + assignment + request in the DB.
#     * Calls on-chain `Escrow::release_escrow` extrinsic (2nd event).
# - /escrows/release-due:
#     * Auto-release for escrows whose auto_release_at has passed.
#     * Intended to be called periodically by a cron/worker.

from __future__ import annotations

import os
import logging
from typing import Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .Database.db import get_db
from .auth_dep import get_current_user
from .models import Assignment, Escrow, Request, User

# Reuse the Substrate helpers from PoBA:
# - get_substrate(): fresh client with auto_reconnect and proper error handling
# - get_signer(): signer from env (SUBSTRATE_SIGNER_URI / SUBSTRATE_SIGNER_MNEMONIC)
from .routes_poba import get_substrate, get_signer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/escrows", tags=["escrows"])

# -------------------------- Substrate / escrow config --------------------------

ESCROW_WAIT_FINALIZATION = os.getenv("ESCROW_WAIT_FINALIZATION", "0").lower() in (
    "1",
    "true",
    "yes",
)

# Optional fallback account when user has no wallet_address configured.
ESCROW_FALLBACK_ACCOUNT = os.getenv("ESCROW_FALLBACK_ACCOUNT", "")


def _uuid16_from_any(val: Any) -> bytes:
    """
    Convert a Python UUID / string into 16-byte array for `[u8;16]` on-chain.
    Matches the representation used in the PoBA pallet.
    """
    from uuid import UUID

    if isinstance(val, UUID):
        u = val
    else:
        u = UUID(str(val))
    return u.bytes


# -------------------------- Helpers --------------------------

def _get_user_id(user: Any) -> str:
    """
    Extracts the authenticated user's ID from the dependency payload.
    Raises 401 if the ID is missing.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if isinstance(user, dict):
        uid = user.get("id") or user.get("user_id")
        if not uid:
            raise HTTPException(status_code=401, detail="Invalid user payload (no id)")
        return str(uid)
    uid = getattr(user, "id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user payload (no id)")
    return str(uid)


def _get_wallet_address_for_user(db: Session, user_id: Any) -> str:
    """
    Load the on-chain wallet address for a given app user.
    Falls back to ESCROW_FALLBACK_ACCOUNT if not set.

    Assumes:
      * models.User has a `wallet_address` column (text).
    """
    user: Optional[User] = db.query(User).filter(User.id == user_id).first()
    if user and getattr(user, "wallet_address", None):
        return str(user.wallet_address)

    if ESCROW_FALLBACK_ACCOUNT:
        logger.warning(
            "[escrow] User %s has no wallet_address; using ESCROW_FALLBACK_ACCOUNT %s",
            user_id,
            ESCROW_FALLBACK_ACCOUNT,
        )
        return ESCROW_FALLBACK_ACCOUNT

    raise HTTPException(
        status_code=500,
        detail="User has no wallet_address configured and ESCROW_FALLBACK_ACCOUNT is not set",
    )


# -------------------------- Schemas --------------------------

class EscrowInitiateIn(BaseModel):
    assignment_id: str


class EscrowConfirmIn(BaseModel):
    assignment_id: str


class EscrowOut(BaseModel):
    id: str
    assignment_id: str
    payer_user_id: str
    payee_user_id: str
    amount_cents: int
    status: str
    created_at: datetime
    updated_at: datetime
    # Optional timestamps for the new flow
    driver_marked_completed_at: Optional[datetime] = None
    sender_confirmed_at: Optional[datetime] = None
    auto_release_at: Optional[datetime] = None


# -------------------------- On-chain helpers --------------------------

def _create_onchain_escrow_for_assignment(
    db: Session,
    asg: Assignment,
    req: Request,
    amount_cents: int,
) -> None:
    """
    Compose and submit the `Escrow::create_escrow` extrinsic.

    Mapping:
      request_uuid -> req.id (DB UUID)
      offer_uuid   -> asg.offer_id (DB UUID, FK to courier_offers)
      driver       -> driver's wallet_address
      payer        -> request owner's wallet_address
      amount       -> amount_cents (1 chain unit = 1 cent for now)

    If submission fails, this function raises an exception and the caller
    should roll back the DB transaction.
    """
    # We expect Assignment to carry the related offer UUID.
    offer_id = getattr(asg, "offer_id", None)
    if not offer_id:
        raise HTTPException(
            status_code=500,
            detail="Assignment has no offer_id; cannot create on-chain escrow",
        )

    request_uuid_bytes = _uuid16_from_any(req.id)
    offer_uuid_bytes = _uuid16_from_any(offer_id)

    # Resolve on-chain AccountIds for driver and payer.
    driver_address = _get_wallet_address_for_user(db, asg.driver_user_id)
    payer_address = _get_wallet_address_for_user(db, req.owner_user_id)

    substrate = get_substrate()
    signer = get_signer()

    call = substrate.compose_call(
        call_module="Escrow",
        call_function="create_escrow",
        call_params={
            "request_uuid": request_uuid_bytes,
            "offer_uuid": offer_uuid_bytes,
            "driver": driver_address,
            "payer": payer_address,
            "amount": amount_cents,
        },
    )

    extrinsic = substrate.create_signed_extrinsic(call=call, keypair=signer)

    wait_args = {}
    if ESCROW_WAIT_FINALIZATION:
        wait_args["wait_for_finalization"] = True
    else:
        wait_args["wait_for_inclusion"] = True

    try:
        receipt = substrate.submit_extrinsic(extrinsic, **wait_args)
    except Exception as e:
        logger.exception("[escrow] submit_extrinsic(create_escrow) failed")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to submit create_escrow extrinsic: {e}",
        )

    if not getattr(receipt, "is_success", False):
        logger.error(
            "[escrow] create_escrow extrinsic failed: %s",
            getattr(receipt, "error_message", None),
        )
        raise HTTPException(
            status_code=502,
            detail=(
                f"create_escrow extrinsic failed: "
                f"{getattr(receipt, 'error_message', 'unknown error')}"
            ),
        )

    logger.info(
        "[escrow] create_escrow OK (hash=%s, amount_cents=%s)",
        getattr(receipt, "extrinsic_hash", None),
        amount_cents,
    )


def _release_onchain_escrow_for_assignment(
    asg: Assignment,
    req: Request,
) -> None:
    """
    Compose and submit the `Escrow::release_escrow` extrinsic.

    Called when:
      - Sender confirms delivery (manual release), OR
      - In future, auto-release cron might also call this.

    Signature assumed:
      Escrow::release_escrow(
        origin,
        request_uuid: [u8;16],
        offer_uuid: [u8;16],
      )
    """
    offer_id = getattr(asg, "offer_id", None)
    if not offer_id:
        raise HTTPException(
            status_code=500,
            detail="Assignment has no offer_id; cannot release on-chain escrow",
        )

    request_uuid_bytes = _uuid16_from_any(req.id)
    offer_uuid_bytes = _uuid16_from_any(offer_id)

    substrate = get_substrate()
    signer = get_signer()

    call = substrate.compose_call(
        call_module="Escrow",
        call_function="release_escrow",
        call_params={
            "request_uuid": request_uuid_bytes,
            "offer_uuid": offer_uuid_bytes,
        },
    )

    extrinsic = substrate.create_signed_extrinsic(call=call, keypair=signer)

    wait_args = {}
    if ESCROW_WAIT_FINALIZATION:
        wait_args["wait_for_finalization"] = True
    else:
        wait_args["wait_for_inclusion"] = True

    try:
        receipt = substrate.submit_extrinsic(extrinsic, **wait_args)
    except Exception as e:
        logger.exception("[escrow] submit_extrinsic(release_escrow) failed")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to submit release_escrow extrinsic: {e}",
        )

    if not getattr(receipt, "is_success", False):
        logger.error(
            "[escrow] release_escrow extrinsic failed: %s",
            getattr(receipt, "error_message", None),
        )
        raise HTTPException(
            status_code=502,
            detail=(
                f"release_escrow extrinsic failed: "
                f"{getattr(receipt, 'error_message', 'unknown error')}"
            ),
        )

    logger.info(
        "[escrow] release_escrow OK (hash=%s)",
        getattr(receipt, "extrinsic_hash", None),
    )


# -------------------------- Routes --------------------------

@router.post("/initiate", response_model=EscrowOut, status_code=status.HTTP_201_CREATED)
def initiate_escrow(
    payload: EscrowInitiateIn,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    """
    Create (or return existing) escrow for an assignment AND call the
    on-chain Escrow::create_escrow extrinsic.

    Flow:
      1) Only the request owner (payer) may call this endpoint.
      2) Assignment must exist and have a positive agreed_price_cents.
      3) If an Escrow already exists and assignment is in a later payment
         stage, we simply return the existing row (idempotent).
      4) Otherwise:
           * Create a new Escrow row with status=pending_deposit.
           * Set assignment.payment_status=pending_deposit.
           * Call on-chain `create_escrow`.
           * Commit the DB transaction only if the extrinsic succeeds.

    When this endpoint succeeds, you should see `EscrowCreated` event
    in the chain explorer for the same (request_uuid, offer_uuid).
    """
    uid = _get_user_id(user)

    # 1) Load assignment + request
    asg: Optional[Assignment] = (
        db.query(Assignment)
        .filter(Assignment.id == payload.assignment_id)
        .first()
    )
    if not asg:
        raise HTTPException(status_code=404, detail="Assignment not found")

    req: Optional[Request] = (
        db.query(Request)
        .filter(Request.id == asg.request_id)
        .first()
    )
    if not req:
        raise HTTPException(
            status_code=500,
            detail="Request row missing for assignment",
        )

    # 2) Ensure caller is the payer (request owner)
    if str(req.owner_user_id) != str(uid):
        raise HTTPException(
            status_code=403,
            detail="Only the request owner can initiate payment for this assignment",
        )

    # 3) Validate agreed price
    if asg.agreed_price_cents is None or int(asg.agreed_price_cents) <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Assignment has no positive agreed_price_cents; "
                "cannot create escrow"
            ),
        )
    amount_cents = int(asg.agreed_price_cents)

    # 4) Validate payment status allowed to start (simple state gate)
    allowed_start_status = {"pending_deposit", "failed", "refunded", "cancelled"}
    ps = str(getattr(asg, "payment_status", "pending_deposit"))

    # If there is already an Escrow AND we are already in a later stage,
    # return existing escrow (idempotent behaviour).
    if asg.escrow is not None and ps not in allowed_start_status:
        e = asg.escrow
        now = datetime.now(timezone.utc)
        return EscrowOut(
            id=str(e.id),
            assignment_id=str(e.assignment_id),
            payer_user_id=str(e.payer_user_id),
            payee_user_id=str(e.payee_user_id),
            amount_cents=int(e.amount_cents),
            status=str(e.status),
            created_at=e.created_at or now,
            updated_at=e.updated_at or now,
            driver_marked_completed_at=getattr(e, "driver_marked_completed_at", None),
            sender_confirmed_at=getattr(e, "sender_confirmed_at", None),
            auto_release_at=getattr(e, "auto_release_at", None),
        )

    # 5) If escrow already exists but we are allowed to (re)start, just reuse it
    #    and DO NOT call on-chain again (we assume it was already done).
    if asg.escrow is not None and ps in allowed_start_status:
        e = asg.escrow
        now = datetime.now(timezone.utc)
        return EscrowOut(
            id=str(e.id),
            assignment_id=str(e.assignment_id),
            payer_user_id=str(e.payer_user_id),
            payee_user_id=str(e.payee_user_id),
            amount_cents=int(e.amount_cents),
            status=str(e.status),
            created_at=e.created_at or now,
            updated_at=e.updated_at or now,
            driver_marked_completed_at=getattr(e, "driver_marked_completed_at", None),
            sender_confirmed_at=getattr(e, "sender_confirmed_at", None),
            auto_release_at=getattr(e, "auto_release_at", None),
        )

    # 6) Create a new Escrow row + align assignment.payment_status,
    #    but DO NOT commit yet – we commit only after the extrinsic succeeds.
    e = Escrow(
        assignment_id=asg.id,
        payer_user_id=req.owner_user_id,
        payee_user_id=asg.driver_user_id,
        amount_cents=amount_cents,
        status="pending_deposit",
    )
    db.add(e)
    asg.payment_status = "pending_deposit"

    try:
        if DEMO_MODE:
            logger.warning("[DEMO MODE] skipping blockchain escrow creation")
        else:
            _create_onchain_escrow_for_assignment(db, asg, req, amount_cents)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e_generic:
        db.rollback()
        logger.exception("[escrow] Unexpected error in initiate_escrow")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error in initiate_escrow: {e_generic}",
        )

    # 9) Refresh and return
    db.refresh(e)
    db.refresh(asg)

    now = datetime.now(timezone.utc)
    return EscrowOut(
        id=str(e.id),
        assignment_id=str(e.assignment_id),
        payer_user_id=str(e.payer_user_id),
        payee_user_id=str(e.payee_user_id),
        amount_cents=int(e.amount_cents),
        status=str(e.status),
        created_at=e.created_at or now,
        updated_at=e.updated_at or now,
        driver_marked_completed_at=getattr(e, "driver_marked_completed_at", None),
        sender_confirmed_at=getattr(e, "sender_confirmed_at", None),
        auto_release_at=getattr(e, "auto_release_at", None),
    )


@router.post("/confirm-delivered", response_model=EscrowOut)
def confirm_delivered(
    payload: EscrowConfirmIn,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    """
    Called by the request owner (sender / rider) to confirm that the package
    or ride was delivered.

    Effects:
      - Only allowed if:
          * assignment exists
          * caller is request.owner_user_id
          * assignment.status == 'completed'
          * escrow exists and is in a releasable state (e.g. deposited)
      - Updates (DB):
          * escrow.status = 'released'
          * escrow.sender_confirmed_at = now
          * escrow.auto_release_at = now (if not already set)
          * assignment.payment_status = 'released'
          * request.status = 'completed' (so it moves to the "completed" list)
      - On-chain:
          * Calls Escrow::release_escrow(request_uuid, offer_uuid),
            emitting an `EscrowReleased` (or similar) event.
    """
    uid = _get_user_id(user)

    asg: Optional[Assignment] = (
        db.query(Assignment)
        .filter(Assignment.id == payload.assignment_id)
        .first()
    )
    if not asg:
        raise HTTPException(status_code=404, detail="Assignment not found")

    req: Optional[Request] = (
        db.query(Request)
        .filter(Request.id == asg.request_id)
        .first()
    )
    if not req:
        raise HTTPException(
            status_code=500,
            detail="Request row missing for assignment",
        )

    # Ensure caller is the request owner (payer)
    if str(req.owner_user_id) != str(uid):
        raise HTTPException(
            status_code=403,
            detail="Only the request owner can confirm delivery for this assignment",
        )

    # Require that the logistics side is already completed
    if str(asg.status) != "completed":
        raise HTTPException(
            status_code=400,
            detail="Assignment must be completed before confirming delivery",
        )

    esc: Optional[Escrow] = asg.escrow
    if esc is None:
        raise HTTPException(
            status_code=400,
            detail="No escrow exists for this assignment",
        )

    # Guard: escrow must be in a releasable payment state
    # In a stricter production flow you might require esc.status == "deposited".
    if str(esc.status) not in {"pending_deposit", "deposited"}:
        raise HTTPException(
            status_code=400,
            detail=f"Escrow is in status '{esc.status}', cannot release",
        )

    now = datetime.now(timezone.utc)

    # Update DB objects but do not commit until the extrinsic succeeds
    esc.sender_confirmed_at = now
    esc.status = "released"
    if getattr(esc, "auto_release_at", None) is None:
        esc.auto_release_at = now

    # Mark request as completed so it moves from "active" to "completed" lists
    req.status = "completed"
    req.updated_at = now

    asg.payment_status = "released"

    db.add(esc)
    db.add(asg)
    db.add(req)

    try:
        # On-chain release – 2nd escrow-related event on the chain.
        _release_onchain_escrow_for_assignment(asg, req)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e_generic:
        db.rollback()
        logger.exception("[escrow] Unexpected error in confirm_delivered")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error in confirm_delivered: {e_generic}",
        )

    db.refresh(esc)
    db.refresh(asg)

    return EscrowOut(
        id=str(esc.id),
        assignment_id=str(esc.assignment_id),
        payer_user_id=str(esc.payer_user_id),
        payee_user_id=str(esc.payee_user_id),
        amount_cents=int(esc.amount_cents),
        status=str(esc.status),
        created_at=esc.created_at or now,
        updated_at=esc.updated_at or now,
        driver_marked_completed_at=getattr(esc, "driver_marked_completed_at", None),
        sender_confirmed_at=getattr(esc, "sender_confirmed_at", None),
        auto_release_at=getattr(esc, "auto_release_at", None),
    )


@router.post("/release-due")
def release_due(db: Session = Depends(get_db)):
    """
    Auto-release escrows whose auto_release_at has passed.

    Intended for a periodic cron/worker:
      - Finds escrows with:
          * status in ('deposited', 'pending_deposit')  [configurable]
          * auto_release_at IS NOT NULL
          * auto_release_at <= now
      - Sets:
          * escrow.status = 'released'
          * escrow.sender_confirmed_at (if empty) = now
          * assignment.payment_status = 'released'

    NOTE:
      Currently this only updates the DB. If you want on-chain events for
      auto-release as well, you can extend this to call
      `_release_onchain_escrow_for_assignment` per escrow (similar to
      confirm_delivered), but that is left as a future enhancement.
    """
    now = datetime.now(timezone.utc)

    # You can tighten this to only 'deposited' in production if you want.
    candidates: list[Escrow] = (
        db.query(Escrow)
        .filter(
            Escrow.status.in_(["deposited", "pending_deposit"]),
            Escrow.auto_release_at.isnot(None),
            Escrow.auto_release_at <= now,
        )
        .all()
    )

    released_count = 0

    for esc in candidates:
        esc.status = "released"
        if getattr(esc, "sender_confirmed_at", None) is None:
            esc.sender_confirmed_at = now

        if esc.assignment is not None:
            esc.assignment.payment_status = "released"

        db.add(esc)
        released_count += 1

    if released_count:
        db.commit()

    return {"ok": True, "released": released_count}
