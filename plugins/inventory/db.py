"""
db/inventory_db.py
All query logic for parts, vendors, and stock transactions.
Ported from inventory/db.py — now uses shared get_conn() and single DB file.
"""
from datetime import date
from core.db import get_conn


# ── Table Init (called by core.db.init_db) ───────────────────────────────────

def init_db():
    with get_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS vendors (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                contact TEXT,
                phone   TEXT,
                email   TEXT,
                website TEXT,
                notes   TEXT,
                created TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS parts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                sku           TEXT,
                category      TEXT,
                qty           INTEGER DEFAULT 0,
                reorder_point INTEGER DEFAULT 1,
                cost          REAL,
                sell_price    REAL,
                vendor_id     INTEGER REFERENCES vendors(id),
                location      TEXT,
                notes         TEXT,
                created       TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                type    TEXT,
                part_id INTEGER REFERENCES parts(id),
                qty     INTEGER,
                price   REAL,
                date    TEXT,
                notes   TEXT
            )
        """)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_parts_sku_unique ON parts(sku)")


# ── Vendors ───────────────────────────────────────────────────────────────────

def db_all_vendors():
    with get_conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM vendors ORDER BY name ASC").fetchall()]


def db_insert_vendor(v: dict):
    with get_conn() as con:
        con.execute("""
            INSERT INTO vendors (name,contact,phone,email,website,notes,created)
            VALUES (?,?,?,?,?,?,?)
        """, (v["name"], v.get("contact", ""), v.get("phone", ""),
              v.get("email", ""), v.get("website", ""), v.get("notes", ""),
              date.today().isoformat()))


def db_update_vendor(v: dict):
    with get_conn() as con:
        con.execute("""
            UPDATE vendors SET name=?,contact=?,phone=?,email=?,website=?,notes=?
            WHERE id=?
        """, (v["name"], v.get("contact", ""), v.get("phone", ""),
              v.get("email", ""), v.get("website", ""), v.get("notes", ""), v["id"]))


def db_delete_vendor(vendor_id: int):
    with get_conn() as con:
        con.execute("DELETE FROM vendors WHERE id=?", (vendor_id,))


# ── Parts ─────────────────────────────────────────────────────────────────────

def db_all_parts():
    with get_conn() as con:
        return [dict(r) for r in con.execute("""
            SELECT p.*, v.name as vendor_name
            FROM parts p LEFT JOIN vendors v ON p.vendor_id=v.id
            ORDER BY p.name ASC
        """).fetchall()]


def db_get_part(part_id: int):
    with get_conn() as con:
        row = con.execute("SELECT * FROM parts WHERE id=?", (part_id,)).fetchone()
        return dict(row) if row else None


def db_low_stock_parts():
    with get_conn() as con:
        return [dict(r) for r in con.execute("""
            SELECT p.*, v.name as vendor_name
            FROM parts p LEFT JOIN vendors v ON p.vendor_id=v.id
            WHERE p.qty <= p.reorder_point
            ORDER BY p.qty ASC
        """).fetchall()]


def db_search_parts(query: str):
    q = f"%{query.lower()}%"
    with get_conn() as con:
        return [dict(r) for r in con.execute("""
            SELECT p.*, v.name as vendor_name FROM parts p
            LEFT JOIN vendors v ON p.vendor_id=v.id
            WHERE lower(p.name) LIKE ? OR lower(p.sku) LIKE ?
               OR lower(p.category) LIKE ? OR lower(p.location) LIKE ?
            ORDER BY p.name ASC
        """, (q, q, q, q)).fetchall()]


def db_insert_part(p: dict):
    with get_conn() as con:
        con.execute("""
            INSERT INTO parts
            (name,sku,category,qty,reorder_point,cost,sell_price,vendor_id,location,notes,created)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (p["name"], p.get("sku", ""), p.get("category", ""),
              int(p.get("qty", 0)), int(p.get("reorder_point", 1)),
              p.get("cost"), p.get("sell_price"), p.get("vendor_id"),
              p.get("location", ""), p.get("notes", ""),
              date.today().isoformat()))


def db_update_part(p: dict):
    with get_conn() as con:
        con.execute("""
            UPDATE parts SET
                name=?,sku=?,category=?,qty=?,reorder_point=?,
                cost=?,sell_price=?,vendor_id=?,location=?,notes=?
            WHERE id=?
        """, (p["name"], p.get("sku", ""), p.get("category", ""),
              int(p.get("qty", 0)), int(p.get("reorder_point", 1)),
              p.get("cost"), p.get("sell_price"), p.get("vendor_id"),
              p.get("location", ""), p.get("notes", ""), p["id"]))


def db_adjust_stock(part_id: int, delta: int, notes: str = ""):
    """Add or subtract qty and log a transaction."""
    with get_conn() as con:
        row = con.execute("SELECT qty FROM parts WHERE id=?", (part_id,)).fetchone()
        if not row:
            raise ValueError("Part not found")
        current_qty = row["qty"]
        new_qty = current_qty + delta
        assert new_qty >= 0, f"Stock cannot fall below zero (current: {current_qty}, delta: {delta})"
        con.execute("UPDATE parts SET qty = ? WHERE id=?", (new_qty, part_id))
        con.execute("""
            INSERT INTO transactions (type,part_id,qty,date,notes)
            VALUES (?,?,?,?,?)
        """, ("adjustment", part_id, delta,
              date.today().isoformat(), notes))


def db_delete_part(part_id: int):
    with get_conn() as con:
        con.execute("DELETE FROM parts WHERE id=?", (part_id,))


# ── Stats ─────────────────────────────────────────────────────────────────────

def db_inventory_stats():
    with get_conn() as con:
        total_parts = con.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
        low_stock   = con.execute(
            "SELECT COUNT(*) FROM parts WHERE qty <= reorder_point").fetchone()[0]
        total_value = con.execute(
            "SELECT SUM(qty * cost) FROM parts").fetchone()[0] or 0.0
    return {
        "total_parts": total_parts,
        "low_stock":   low_stock,
        "total_value": f"${total_value:,.2f}",
    }
