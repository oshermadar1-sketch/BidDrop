import os
from dotenv import load_dotenv
load_dotenv()

NODE_WS_URL = os.getenv("NODE_WS_URL", "ws://127.0.0.1:9944")
SS58_FORMAT = int(os.getenv("SS58_FORMAT", "42"))
SERVICE_SEED = os.getenv("SERVICE_SEED", "//Alice")
EPSILON_MS = int(os.getenv("EPSILON_MS", "1000"))      # מרווח בטיחות לפני תחילת הסלוט
LOOKAHEAD_SLOTS = int(os.getenv("LOOKAHEAD_SLOTS", "3"))  # כמה סלוטים קדימה לחפש
