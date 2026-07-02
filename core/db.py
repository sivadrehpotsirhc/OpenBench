import contextlib
import sqlite3
from config import DB_PATH
 
 
@contextlib.contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Register custom functions
    from core.utils import _parse_date, safe_float
    def sql_parse_date(s):
        if not s:
            return None
        d = _parse_date(s)
        return d.isoformat() if d else None
        
    conn.create_function("parse_date", 1, sql_parse_date)
    conn.create_function("safe_float", 1, lambda v: safe_float(v))
    
    try:
        with conn:
            yield conn
    finally:
        conn.close()
 
 
def init_db():
    from core.settings  import _init_settings
    _init_settings()
    with get_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS pins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                role TEXT DEFAULT 'technician',
                created TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT,
                phone   TEXT UNIQUE,
                email   TEXT,
                address TEXT,
                notes   TEXT,
                created TEXT
            )
        """)