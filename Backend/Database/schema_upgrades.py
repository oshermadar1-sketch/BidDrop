# Backend/Database/schema_upgrades.py
# Small additive schema upgrades applied at server startup. Each statement only ADDS a
# column if it is missing, so it is safe to run on every start and never touches data.
import logging

from sqlalchemy import text

log = logging.getLogger("schema")

UPGRADES = [
    # Courier profile: inputs of the delivery-time model (see models.Users)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS vehicle_type TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS vehicle_condition INTEGER",
    # Push de-duplication timestamps, read by routes_auction.py and written by routes_offers.py
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS push_defer_until TIMESTAMPTZ",
    "ALTER TABLE courier_offers ADD COLUMN IF NOT EXISTS push_defer_until TIMESTAMPTZ",
]


def apply_schema_upgrades(engine) -> None:
    with engine.begin() as conn:
        for sql in UPGRADES:
            conn.execute(text(sql))
    log.info("Schema upgrades checked (%d statements)", len(UPGRADES))
