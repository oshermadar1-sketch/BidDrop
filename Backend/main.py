# Backend/main.py
# FastAPI app with CORS, DB health endpoints, routers, and APScheduler via Lifespan.

from fastapi.middleware.cors import CORSMiddleware

import logging, sys, os
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

# DB deps
from .Database.db import get_db
try:
    from .Database.db import SessionLocal  # session factory for scheduler job
except Exception:  # pragma: no cover
    SessionLocal = None  # fallback

# Routers
from .routes_users import router as users_router
from .routes_auth import router as auth_router
from .routes_sender import router as sender_router
from .routes_rider import router as rider_router
from .routes_courier import router as courier_router
from .routes_requests import router as requests_router
from .routes_offers import router as offers_router
from .routes_devices import router as devices_router
from .routes_auction import router as auction_router
from .routes_assignments import router as assignments_router
from .routes_matching import router as matching_router
from .routes_poba import router as poba_router, install_poba_slot_listener
from .routes_escrow import router as escrow_router

from dotenv import load_dotenv
load_dotenv()

# --------------------------- Auto-matcher toggle ---------------------------
# Legacy IDA* auto-clearing loop (scheduler) can be globally enabled/disabled
# via env var. Default: disabled (BID_AUTO_MATCHER != "1").
AUTO_MATCHER_ENABLED = os.getenv("BID_AUTO_MATCHER", "0") == "1"

# Clearing tick (IDA*)
try:
    from .routes_auction import run_clearing_tick
except Exception:
    try:
        from app.auction.routes_auction import run_clearing_tick  # type: ignore
    except Exception:
        run_clearing_tick = None  # pragma: no cover

# APScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# --------------------------- Logging setup ---------------------------
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def _setup_logger(name: str, filename: str) -> logging.Logger:
    """Create a named logger that logs to rotating file + stdout (for Docker/K8s)."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')

    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, filename),
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    # Avoid duplicate handlers on reload
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(sh)

    return logger

_setup_logger("clearing", "clearing.log")
_setup_logger("match", "matches.log")
_setup_logger("poba", "poba.log")


logger = logging.getLogger("clearing")
scheduler = AsyncIOScheduler()

def _clearing_job():
    """Run one clearing tick in a short-lived DB session."""
    if run_clearing_tick is None or SessionLocal is None:
        logger.warning("Clearing job skipped (missing run_clearing_tick or SessionLocal)")
        return
    db = SessionLocal()
    try:
        res = run_clearing_tick(db=db)
        logger.info("Clearing tick result: %s", res)
    except Exception as e:  # pragma: no cover
        logger.exception("Clearing job failed: %s", e)
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    try:
        # Add new columns the code expects (only if missing; never changes data)
        from .Database.db import engine
        from .Database.schema_upgrades import apply_schema_upgrades
        apply_schema_upgrades(engine)
    except Exception as e:  # pragma: no cover
        logger.exception("Schema upgrade failed: %s", e)

    try:
        if AUTO_MATCHER_ENABLED:
            # IDA* clearing every 60 seconds (legacy auto-matcher loop)
            scheduler.add_job(_clearing_job, IntervalTrigger(seconds=60))
            scheduler.start()
            logger.info(
                "Scheduler started (IDA* every 60s, BID_AUTO_MATCHER=1)"
            )
        else:
            # Auto-matcher is disabled: do not start scheduler at all
            logger.info(
                "Auto-matcher disabled (BID_AUTO_MATCHER != 1) — scheduler not started"
            )
    except Exception as e:  # pragma: no cover
        logger.exception("Failed to start scheduler: %s", e)

    yield

    # ---- Shutdown ----
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped")
    except Exception as e:  # pragma: no cover
        logger.exception("Failed to stop scheduler: %s", e)

app = FastAPI(lifespan=lifespan)

# --------------------------- CORS ---------------------------
# MVP: allow all; tighten in production by setting ALLOW_ORIGINS env (comma-separated).
allow_origins_env = os.getenv("ALLOW_ORIGINS")
allow_origins = [o.strip() for o in allow_origins_env.split(",")] if allow_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------- Health (ready + live) ---------------------------
# Some infra/tools expect /health, others /healthz; PoBA worker can ping /poba/ping.
@app.get("/health")
def health():
    """Basic liveness/ready probe (200 OK)."""
    return {"status": "ok"}

@app.get("/healthz")
def healthz():
    """K8s-style health endpoint (200 OK)."""
    return {"ok": True}

@app.get("/poba/ping")
def poba_ping():
    """Lightweight endpoint for the PoBA worker connectivity check."""
    return {"poba": "ok"}

@app.get("/health/db")
def db_health(db: Session = Depends(get_db)):
    """Returns current DB time to verify DB connectivity."""
    row = db.execute(text("SELECT NOW() AS now")).mappings().first()
    return {"db_time": str(row["now"])}

@app.get("/debug/dbinfo")
def db_info(db: Session = Depends(get_db)):
    """Quick DB identity (database, user, schema)."""
    row = db.execute(
        text("SELECT current_database() as db, current_user as user, current_schema as schema")
    ).mappings().first()
    return dict(row)

# --------------------------- Routers ---------------------------
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(sender_router)
app.include_router(rider_router)
app.include_router(courier_router)
app.include_router(requests_router)
app.include_router(offers_router)
app.include_router(devices_router)
app.include_router(auction_router)
app.include_router(assignments_router)
app.include_router(matching_router)
app.include_router(poba_router)
app.include_router(escrow_router)




#install_poba_slot_listener(app)