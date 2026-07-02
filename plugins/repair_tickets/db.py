"""
db/tickets_db.py
All query logic for tickets, repair logs, and customers.
Ported from ticketing/db.py — logic unchanged, now uses shared get_conn().
"""
import random
import datetime
from datetime import date, timedelta
from core.db import get_conn
from core.utils import _parse_date, safe_float


# ── Table Init (called by core.db.init_db) ───────────────────────────────────

def init_db():
    with get_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id            TEXT PRIMARY KEY,
                priority      TEXT,
                name          TEXT,
                phone         TEXT,
                email         TEXT,
                address       TEXT,
                device        TEXT,
                serial        TEXT,
                repair        TEXT,
                price         TEXT,
                due           TEXT,
                created       TEXT,
                issue         TEXT,
                notes         TEXT,
                status        TEXT DEFAULT 'Open',
                cal_event_id  TEXT,
                technician    TEXT,
                pre_repair_json TEXT,
                tax_exempt    INTEGER DEFAULT 0,
                discount_type TEXT DEFAULT 'None',
                custom_data   TEXT DEFAULT '{}',
                legal_json    TEXT DEFAULT '{}'
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS repair_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT,
                timestamp TEXT,
                status    TEXT,
                note      TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ticket_photos (
                id          TEXT PRIMARY KEY,
                ticket_id   TEXT,
                filename    TEXT,
                uploaded_at TEXT,
                source      TEXT
            )
        """)
        # Safe column additions for existing DBs
        for col, typedef in [("cal_event_id", "TEXT"), ("technician", "TEXT"), ("pre_repair_json", "TEXT"), ("tax_exempt", "INTEGER"), ("discount_type", "TEXT"), ("custom_data", "TEXT DEFAULT '{}'"), ("legal_json", "TEXT DEFAULT '{}'")]:
            try:
                con.execute(f"ALTER TABLE tickets ADD COLUMN {col} {typedef}")
            except Exception:
                pass

        con.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")


# ── Ticket CRUD ───────────────────────────────────────────────────────────────

def db_all_tickets(status: str = None, search: str = None):
    query = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (name LIKE ? OR device LIKE ? OR issue LIKE ? OR lower(id) LIKE ?)"
        search_lower = search.lower()
        params += [f"%{search}%", f"%{search}%", f"%{search}%", f"%{search_lower}%"]
    query += " ORDER BY created DESC"
    with get_conn() as con:
        return [dict(r) for r in con.execute(query, params).fetchall()]


def db_get_ticket(ticket_id: str):
    with get_conn() as con:
        row = con.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None


def db_insert_ticket(ticket: dict):
    with get_conn() as con:
        con.execute("""
            INSERT OR REPLACE INTO tickets
            (id,priority,name,phone,email,address,device,serial,
             repair,price,due,created,issue,notes,status,cal_event_id,technician,pre_repair_json,tax_exempt,discount_type,custom_data,legal_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ticket["id"], ticket["priority"], ticket["name"], ticket["phone"],
            ticket["email"], ticket["address"], ticket["device"], ticket["serial"],
            ticket["repair"], ticket["price"], ticket["due"], ticket["created"],
            ticket["issue"], ticket["notes"], ticket.get("status", "Open"),
            ticket.get("cal_event_id"), ticket.get("technician", ""),
            ticket.get("pre_repair_json", "{}"),
            int(ticket.get("tax_exempt") or 0),
            ticket.get("discount_type", "None"),
            ticket.get("custom_data", "{}"),
            ticket.get("legal_json", "{}")
        ))


def db_update_ticket(ticket: dict):
    with get_conn() as con:
        con.execute("""
            UPDATE tickets SET
                priority=?, name=?, phone=?, email=?, address=?, device=?,
                serial=?, repair=?, price=?, due=?, issue=?, notes=?,
                status=?, cal_event_id=?, technician=?, pre_repair_json=?,
                tax_exempt=?, discount_type=?, custom_data=?, legal_json=?
            WHERE id=?
        """, (
            ticket["priority"], ticket["name"], ticket["phone"], ticket["email"],
            ticket["address"], ticket["device"], ticket["serial"], ticket["repair"],
            ticket["price"], ticket["due"], ticket["issue"], ticket["notes"],
            ticket["status"], ticket.get("cal_event_id"), ticket.get("technician", ""),
            ticket.get("pre_repair_json", "{}"),
            int(ticket.get("tax_exempt") or 0),
            ticket.get("discount_type", "None"),
            ticket.get("custom_data", "{}"),
            ticket.get("legal_json", "{}"),
            ticket["id"]
        ))


def db_update_status(ticket_id: str, status: str):
    with get_conn() as con:
        con.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))


def db_save_cal_event_id(ticket_id: str, event_id: str):
    with get_conn() as con:
        con.execute("UPDATE tickets SET cal_event_id=? WHERE id=?", (event_id, ticket_id))


def db_delete_ticket(ticket_id: str):
    with get_conn() as con:
        con.execute("DELETE FROM repair_log WHERE ticket_id=?", (ticket_id,))
        con.execute("DELETE FROM ticket_photos WHERE ticket_id=?", (ticket_id,))
        con.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))


# ── Repair Log ────────────────────────────────────────────────────────────────

def db_add_log(ticket_id: str, status: str, note: str):
    ts = datetime.datetime.now().strftime("%a, %b %d %Y  %I:%M %p")
    with get_conn() as con:
        con.execute("""
            INSERT INTO repair_log (ticket_id, timestamp, status, note)
            VALUES (?, ?, ?, ?)
        """, (ticket_id, ts, status, note))


def db_get_log(ticket_id: str):
    with get_conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM repair_log WHERE ticket_id=? ORDER BY id DESC",
            (ticket_id,)).fetchall()]


# ── Stats ─────────────────────────────────────────────────────────────────────

def db_ticket_stats():
    with get_conn() as con:
        today_str = date.today().strftime("%a, %b %d %Y")
        open_count = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE status NOT IN ('Completed','Cancelled')"
        ).fetchone()[0]
        due_today = con.execute(
            "SELECT COUNT(*) FROM tickets WHERE due=? AND status NOT IN ('Completed','Cancelled')",
            (today_str,)
        ).fetchone()[0]
        all_open = con.execute(
            "SELECT due FROM tickets WHERE status NOT IN ('Completed','Cancelled')"
        ).fetchall()
        def _is_overdue(due_str):
            d = _parse_date(due_str)
            return d is not None and d < date.today()

        overdue = sum(1 for row in all_open if _is_overdue(row[0]))

        week_start = date.today() - timedelta(days=date.today().weekday())
        completed = con.execute(
            "SELECT price, created FROM tickets WHERE status='Completed'"
        ).fetchall()
        revenue = 0.0
        for price_raw, created_raw in completed:
            created_date = _parse_date(created_raw)
            if created_date and created_date >= week_start:
                revenue += safe_float(price_raw)

    return {
        "open":      open_count,
        "due_today": due_today,
        "overdue":   overdue,
        "revenue":   f"${revenue:,.2f}"
    }


# ── Utilities ─────────────────────────────────────────────────────────────────

def gen_ticket_id():
    with get_conn() as con:
        for _ in range(100):
            rand = random.randint(1000, 9999)
            tid = f"TKT-{date.today().strftime('%y%m%d')}-{rand}"
            if not con.execute("SELECT 1 FROM tickets WHERE id=?", (tid,)).fetchone():
                return tid
        raise RuntimeError("Could not generate a unique ticket ID after 100 attempts")

# ── Photos ────────────────────────────────────────────────────────────────────

def db_add_photo(photo_id: str, ticket_id: str, filename: str, source: str):
    ts = datetime.datetime.now().isoformat()
    with get_conn() as con:
        con.execute("""
            INSERT INTO ticket_photos (id, ticket_id, filename, uploaded_at, source)
            VALUES (?, ?, ?, ?, ?)
        """, (photo_id, ticket_id, filename, ts, source))

def db_get_photos(ticket_id: str):
    with get_conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM ticket_photos WHERE ticket_id=? ORDER BY uploaded_at DESC",
            (ticket_id,)).fetchall()]

def db_delete_photo(ticket_id: str, filename: str):
    with get_conn() as con:
        con.execute("DELETE FROM ticket_photos WHERE ticket_id=? AND filename=?", (ticket_id, filename))

