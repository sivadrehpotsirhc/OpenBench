"""
db/finance_db.py
Database layer for the Finance module in the Web Version.
Unified DB structure.
"""
from datetime import date, datetime
from core.db import get_conn
from core.utils import _parse_date, safe_float

EXPENSE_CATEGORIES = [
    "Supplier / Parts Cost",
    "Operating Expense",
    "Payroll",
    "Rent / Utilities",
    "Equipment",
    "Marketing",
    "Software / Subscriptions",
    "Other",
]

def init_db():
    with get_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT,
                description TEXT,
                amount      REAL,
                category    TEXT,
                source      TEXT,
                notes       TEXT,
                created     TEXT
            )
        """)


# ── Expense CRUD ──────────────────────────────────────────────────────────────

def db_all_expenses():
    with get_conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM expenses ORDER BY date DESC").fetchall()]

def db_insert_expense(e: dict):
    with get_conn() as con:
        con.execute("""
            INSERT INTO expenses (date, description, amount, category, source, notes, created)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (e["date"], e.get("description", ""), safe_float(e["amount"]),
              e.get("category", "Other"), e.get("source", "Manual"),
              e.get("notes", ""), date.today().strftime("%a, %b %d %Y")))

def db_update_expense(e: dict):
    with get_conn() as con:
        con.execute("""
            UPDATE expenses
            SET date=?, description=?, amount=?, category=?, source=?, notes=?
            WHERE id=?
        """, (e["date"], e.get("description", ""), safe_float(e["amount"]),
              e.get("category", "Other"), e.get("source", "Manual"),
              e.get("notes", ""), e["id"]))

def db_delete_expense(eid: int):
    with get_conn() as con:
        con.execute("DELETE FROM expenses WHERE id=?", (eid,))

def db_get_expense(eid: int):
    with get_conn() as con:
        row = con.execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone()
        return dict(row) if row else None

# ── Aggregate Stats ───────────────────────────────────────────────────────────

def db_finance_summary(frm_str: str = None, to_str: str = None):
    """Calculate summary figures for the given date range."""
    if frm_str:
        try:
            datetime.strptime(frm_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid 'from' date format: {frm_str}. Expected YYYY-MM-DD.")
    if to_str:
        try:
            datetime.strptime(to_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid 'to' date format: {to_str}. Expected YYYY-MM-DD.")

    with get_conn() as con:
        # 1. Repair Revenue (from tickets)
        query_tickets = "SELECT SUM(safe_float(price)) as rev, COUNT(*) as cnt FROM tickets WHERE status='Completed'"
        params_tickets = []
        if frm_str:
            query_tickets += " AND parse_date(created) >= ?"
            params_tickets.append(frm_str)
        if to_str:
            query_tickets += " AND parse_date(created) < ?"
            params_tickets.append(to_str)
        row_tickets = con.execute(query_tickets, params_tickets).fetchone()
        repair_rev = row_tickets["rev"] or 0.0
        repair_count = row_tickets["cnt"] or 0

        # 2. Device Revenue & Cost (from devices)
        query_devices = """
            SELECT SUM(safe_float(sell_price)) as rev, SUM(safe_float(purchase_price)) as cost, COUNT(*) as cnt 
            FROM devices 
            WHERE status='Sold' AND date_sold IS NOT NULL AND deleted = 0
        """
        params_devices = []
        if frm_str:
            query_devices += " AND parse_date(date_sold) >= ?"
            params_devices.append(frm_str)
        if to_str:
            query_devices += " AND parse_date(date_sold) < ?"
            params_devices.append(to_str)
        row_devices = con.execute(query_devices, params_devices).fetchone()
        device_rev = row_devices["rev"] or 0.0
        device_cost = row_devices["cost"] or 0.0
        device_count = row_devices["cnt"] or 0

        # 3. Expenses
        query_expenses = "SELECT SUM(safe_float(amount)) as total FROM expenses WHERE 1=1"
        params_expenses = []
        if frm_str:
            query_expenses += " AND parse_date(date) >= ?"
            params_expenses.append(frm_str)
        if to_str:
            query_expenses += " AND parse_date(date) < ?"
            params_expenses.append(to_str)
        row_expenses = con.execute(query_expenses, params_expenses).fetchone()
        exp_total = row_expenses["total"] or 0.0

    total_rev = repair_rev + device_rev
    total_cost = device_cost + exp_total
    net_profit = total_rev - total_cost

    return {
        "repair_revenue":  repair_rev,
        "device_revenue":  device_rev,
        "total_revenue":   total_rev,
        "device_cost":     device_cost,
        "expense_total":   exp_total,
        "total_cost":      total_cost,
        "net_profit":      net_profit,
        "repair_count":    repair_count,
        "device_count":    device_count,
    }
