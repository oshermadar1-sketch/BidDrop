# Backend/Database/schema_upgrades.py
# Small additive schema upgrades applied at server startup. Each UPGRADES statement only
# ADDS a column if it is missing; DATA_REPAIRS only update rows that are out of step.
# Both are safe to run on every start.
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
    # Route-based estimate for an assignment (services/route_estimates.py)
    "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS route_distance_km NUMERIC",
    "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS route_duration_min NUMERIC",
    "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS estimated_arrival_at TIMESTAMPTZ",
    # Email + password accounts (routes_account.py): the wallet becomes optional and is
    # linked later, when a payment needs it
    "ALTER TABLE users ALTER COLUMN wallet_address DROP NOT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ",
    "CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email))",
    """CREATE TABLE IF NOT EXISTS email_tokens (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        purpose TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL,
        used_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
]


# Data repairs: idempotent statements that fix rows written before a bug was fixed.
DATA_REPAIRS = [
    # Requests whose assignment moved on while the request stayed "assigned" (fixed in
    # routes_assignments.update_assignment_status): bring them in line with the assignment.
    """UPDATE requests r SET status = 'completed'
       FROM assignments a
       WHERE a.request_id = r.id AND a.status = 'completed'
         AND r.status IN ('assigned', 'in_transit')""",
    """UPDATE requests r SET status = 'in_transit'
       FROM assignments a
       WHERE a.request_id = r.id AND a.status IN ('picked_up', 'in_transit')
         AND r.status = 'assigned'""",
]


def apply_schema_upgrades(engine) -> None:
    with engine.begin() as conn:
        for sql in UPGRADES:
            conn.execute(text(sql))
        for sql in DATA_REPAIRS:
            conn.execute(text(sql))
    log.info("Schema upgrades checked (%d statements, %d data repairs)", len(UPGRADES), len(DATA_REPAIRS))
