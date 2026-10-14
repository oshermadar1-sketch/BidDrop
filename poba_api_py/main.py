import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from substrateinterface import SubstrateInterface, Keypair
from .routers import auctions
from .services.auction_scheduler import start_scheduler

load_dotenv()
SUB_WS = os.getenv("SUBSTRATE_WS", "ws://127.0.0.1:9944")

# Development account only (Alice)
ALICE = Keypair.create_from_uri("//Alice")

# ---------- Stable connection: create a new connection for each request ----------
def get_substrate():
    try:
        sub = SubstrateInterface(url=SUB_WS, auto_reconnect=True)
        sub.init_runtime()  # Load runtime metadata so that compose_call works
        _ = sub.get_chain_head()  # Simple health check
        return sub
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"cannot connect to node: {e}")

# ---------- Request models ----------
class CreateShipmentIn(BaseModel):
    detailsURI: str
    deadline: int  # Unix seconds timestamp

class PlaceBidIn(BaseModel):
    price: int

# ---------- Lifespan handler ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_scheduler()
    yield
    # Shutdown

app = FastAPI(title="PoBA API (FastAPI)", lifespan=lifespan)

# ---------- Middleware ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ---------- Routers ----------
app.include_router(auctions.router)

# ---------- Debug endpoints ----------
@app.get("/debug/health")
def debug_health():
    sub = get_substrate()
    head = sub.get_chain_head()
    return {"ok": True, "head": head}

@app.get("/debug/modules")
def debug_modules():
    sub = get_substrate()
    modules = sub.get_metadata_modules()
    return [m["name"] if isinstance(m, dict) else m.value["name"] for m in modules]

# ---------- API root ----------
@app.get("/")
def root():
    return {"ok": True}

# ---------- Business logic endpoints ----------
@app.post("/shipments")
def create_shipment(body: CreateShipmentIn):
    sub = get_substrate()
    try:
        call = sub.compose_call(
            call_module="Poba",
            call_function="create_shipment",
            call_params={"details_uri": body.detailsURI.encode(), "deadline": body.deadline},
        )
        xt = sub.create_signed_extrinsic(call=call, keypair=ALICE)
        receipt = sub.submit_extrinsic(xt, wait_for_inclusion=True)
    except Exception as e:
        raise HTTPException(500, f"submit failed: {e}")

    if not receipt.is_success:
        raise HTTPException(500, f"Extrinsic failed: {receipt.error_message}")

    next_id = sub.query(module="Poba", storage_function="NextShipmentId").value
    return {"id": next_id - 1}

@app.post("/shipments/{sid}/bids")
def place_bid(sid: int, body: PlaceBidIn):
    sub = get_substrate()
    try:
        call = sub.compose_call("Poba", "place_bid", {"id": sid, "price": int(body.price)})
        xt = sub.create_signed_extrinsic(call=call, keypair=ALICE)
        receipt = sub.submit_extrinsic(xt, wait_for_inclusion=True)
    except Exception as e:
        raise HTTPException(500, f"submit failed: {e}")
    if not receipt.is_success:
        raise HTTPException(500, f"Extrinsic failed: {receipt.error_message}")
    return {"ok": True}

@app.post("/shipments/{sid}/close")
def close_auction(sid: int):
    sub = get_substrate()
    try:
        call = sub.compose_call("Poba", "close_auction", {"id": sid})
        xt = sub.create_signed_extrinsic(call=call, keypair=ALICE)
        receipt = sub.submit_extrinsic(xt, wait_for_inclusion=True)
    except Exception as e:
        raise HTTPException(500, f"submit failed: {e}")
    if not receipt.is_success:
        raise HTTPException(500, f"Extrinsic failed: {receipt.error_message}")
    return {"ok": True}

@app.post("/shipments/{sid}/declare")
def declare_winner(sid: int):
    sub = get_substrate()
    try:
        call = sub.compose_call("Poba", "declare_winner", {"id": sid})
        xt = sub.create_signed_extrinsic(call=call, keypair=ALICE)
        receipt = sub.submit_extrinsic(xt, wait_for_inclusion=True)
    except Exception as e:
        raise HTTPException(500, f"submit failed: {e}")
    if not receipt.is_success:
        raise HTTPException(500, f"Extrinsic failed: {receipt.error_message}")
    s = sub.query(module="Poba", storage_function="Shipments", params=[sid])
    return {"ok": True, "state": s.value}

@app.get("/shipments/{sid}")
def get_shipment(sid: int):
    sub = get_substrate()
    s = sub.query(module="Poba", storage_function="Shipments", params=[sid])
    b = sub.query(module="Poba", storage_function="Bids", params=[sid])
    if s.value is None:
        raise HTTPException(404, "shipment not found")
    return {"shipment": s.value, "bids": b.value or []}
