import os

# Tests never call the real weather service.
os.environ["WEATHER_API_ENABLED"] = "0"

# Tests never use the real database from .env: Backend/Database/db.py reads DATABASE_URL
# when a route module is imported. The engine is lazy, so the placeholder is never connected to.
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg2://unused@localhost/unused"
)
