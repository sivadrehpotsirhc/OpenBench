"""
db/buysell_db.py
All query logic for the buy/sell devices module.
Ported from buysell/db.py — migration logic dropped (fresh unified DB).
"""
from datetime import date
from core.db import get_conn


# ── Table Init (called by core.db.init_db) ───────────────────────────────────

def init_db():
    with get_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name   TEXT,
                customer_phone  TEXT,
                device          TEXT,
                condition       TEXT,
                purchase_price  REAL,
                sell_price      REAL,
                status          TEXT DEFAULT 'Staging',
                notes           TEXT,
                date_acquired   TEXT,
                date_sold       TEXT,
                deleted         INTEGER DEFAULT 0
            )
        """)
        try:
            con.execute("ALTER TABLE devices ADD COLUMN deleted INTEGER DEFAULT 0")
        except Exception:
            pass


# ── Device CRUD ───────────────────────────────────────────────────────────────

def db_all_devices(status: str = None, search: str = None):
    query = "SELECT * FROM devices WHERE deleted = 0"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (device LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ?)"
        params += [f"%{search}%"] * 3
    query += " ORDER BY date_acquired DESC"
    with get_conn() as con:
        return [dict(r) for r in con.execute(query, params).fetchall()]


def db_get_device(device_id: int):
    with get_conn() as con:
        row = con.execute("SELECT * FROM devices WHERE id=? AND deleted = 0", (device_id,)).fetchone()
        return dict(row) if row else None


def db_insert_device(d: dict):
    date_sold = date.today().strftime("%a, %b %d %Y") if d.get("status") == "Sold" else d.get("date_sold", "")
    with get_conn() as con:
        con.execute("""
            INSERT INTO devices
            (customer_name,customer_phone,device,condition,purchase_price,
             sell_price,status,notes,date_acquired,date_sold)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (d.get("customer_name", ""), d.get("customer_phone", ""),
              d["device"], d.get("condition", "Good"),
              d.get("purchase_price"), d.get("sell_price"),
              d.get("status", "Staging"), d.get("notes", ""),
              date.today().strftime("%a, %b %d %Y"), date_sold))


def db_update_device(d: dict):
    date_sold = d.get("date_sold", "")
    if d.get("status") == "Sold" and not date_sold:
        date_sold = date.today().strftime("%a, %b %d %Y")
    with get_conn() as con:
        con.execute("""
            UPDATE devices SET
                customer_name=?,customer_phone=?,device=?,condition=?,
                purchase_price=?,sell_price=?,status=?,notes=?,date_sold=?
            WHERE id=?
        """, (d.get("customer_name", ""), d.get("customer_phone", ""),
              d["device"], d.get("condition", "Good"),
              d.get("purchase_price"), d.get("sell_price"),
              d.get("status", "Staging"), d.get("notes", ""),
              date_sold, d["id"]))


def db_delete_device(device_id: int):
    with get_conn() as con:
        con.execute("UPDATE devices SET deleted = 1 WHERE id=?", (device_id,))


# ── Stats ─────────────────────────────────────────────────────────────────────

def db_buysell_stats():
    with get_conn() as con:
        staging  = con.execute(
            "SELECT COUNT(*) FROM devices WHERE status='Staging' AND deleted = 0").fetchone()[0]
        ready    = con.execute(
            "SELECT COUNT(*) FROM devices WHERE status='Ready for Sale' AND deleted = 0").fetchone()[0]
        sold     = con.execute(
            "SELECT COUNT(*) FROM devices WHERE status='Sold' AND deleted = 0").fetchone()[0]
        revenue  = con.execute(
            "SELECT SUM(sell_price) FROM devices WHERE status='Sold' AND deleted = 0").fetchone()[0] or 0.0
        cost     = con.execute(
            "SELECT SUM(purchase_price) FROM devices WHERE status='Sold' AND deleted = 0").fetchone()[0] or 0.0
    return {
        "staging":       staging,
        "ready":         ready,
        "sold":          sold,
        "total_devices": staging + ready + sold,
        "total_revenue": f"${revenue:,.2f}",
        "total_cost":    f"${cost:,.2f}",
        "profit":        f"${revenue - cost:,.2f}",
    }
