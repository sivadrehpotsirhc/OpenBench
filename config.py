import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── database ──────────────────────────────────────────────────────────────────
# single db file — all three modules share one SQLite file.
# tables are separated by their names (tickets, parts, devices, vendors, etc.)
DB_PATH = os.path.join(DATA_DIR, "30orless.db")

# ── google Calendar api ───────────────────────────────────────────────────────────
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials", "credentials.json")
TOKEN_PATH       = os.path.join(BASE_DIR, "credentials", "token.json")
CALENDAR_ID      = "contact.30orless@gmail.com"

# ── server shiz ────────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8000


