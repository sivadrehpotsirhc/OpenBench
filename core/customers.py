from datetime import date
from core.db import get_conn
from core.utils import safe_float

def db_upsert_customer(ticket: dict):
    phone = (ticket.get("phone") or "").strip()
    if not phone:
        return
    created = ticket.get("created", date.today().strftime("%a, %b %d %Y"))
    with get_conn() as con:
        existing = con.execute(
            "SELECT id FROM customers WHERE phone=?", (phone,)
        ).fetchone()
        if existing:
            con.execute(
                "UPDATE customers SET name=?, email=?, address=? WHERE phone=?",
                (ticket.get("name", ""), ticket.get("email", ""),
                 ticket.get("address", ""), phone)
            )
        else:
            con.execute("""
                INSERT INTO customers (name, phone, email, address, notes, created)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ticket.get("name", ""), phone, ticket.get("email", ""),
                  ticket.get("address", ""), "", created))


def db_all_customers():
    with get_conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM customers ORDER BY name ASC").fetchall()]


def db_search_customers(query: str):
    q = f"%{query.lower()}%"
    with get_conn() as con:
        return [dict(r) for r in con.execute("""
            SELECT * FROM customers
            WHERE lower(name) LIKE ? OR phone LIKE ? OR lower(email) LIKE ?
            ORDER BY name ASC
        """, (q, q, q)).fetchall()]


def db_get_customer_tickets(phone: str):
    with get_conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM tickets WHERE phone=? ORDER BY created DESC",
            (phone,)).fetchall()]


def db_update_customer_notes(phone: str, notes: str):
    with get_conn() as con:
        con.execute("UPDATE customers SET notes=? WHERE phone=?", (notes, phone))


def db_get_customer_stats(phone: str):
    with get_conn() as con:
        rows = con.execute(
            "SELECT price, status FROM tickets WHERE phone=?", (phone,)
        ).fetchall()
    total_tickets = len(rows)
    completed = sum(1 for r in rows if r[1] == "Completed")
    revenue = sum(safe_float(r[0]) for r in rows if r[1] == "Completed")
    return {"total": total_tickets, "completed": completed, "revenue": f"${revenue:,.2f}"}
