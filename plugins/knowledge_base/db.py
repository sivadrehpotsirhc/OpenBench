import datetime
import sqlite3
import logging

logger = logging.getLogger(__name__)
from core.db import get_conn
from core.utils import _parse_date

def init_db():
    with get_conn() as con:
        # Create knowledge bites table
        con.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_bites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device TEXT NOT NULL,
                problem TEXT NOT NULL,
                solution TEXT NOT NULL,
                source_ticket_id TEXT UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        # Create indexes for performance
        con.execute("CREATE INDEX IF NOT EXISTS idx_kb_source_ticket ON knowledge_bites(source_ticket_id)")
        try:
            con.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")
        except sqlite3.OperationalError as oe:
            logger.warning("Could not create index idx_tickets_status on tickets table: %s", oe)
    
    # Run the bootstrap sync of existing completed tickets
    try:
        db_sync_completed_tickets()
    except Exception as e:
        logger.warning("Failed to run bootstrap sync: %s", e)

def db_all_knowledge_bites(search: str = None):
    query = "SELECT * FROM knowledge_bites WHERE 1=1"
    params = []
    if search:
        query += " AND (device LIKE ? OR problem LIKE ? OR solution LIKE ?)"
        like_search = f"%{search}%"
        params += [like_search, like_search, like_search]
    query += " ORDER BY created_at DESC, id DESC"
    with get_conn() as con:
        return [dict(r) for r in con.execute(query, params).fetchall()]

def db_insert_knowledge_bite(device: str, problem: str, solution: str, source_ticket_id: str = None, created_at: str = None):
    if not created_at:
        created_at = datetime.date.today().strftime("%Y-%m-%d")
    with get_conn() as con:
        con.execute("""
            INSERT INTO knowledge_bites (device, problem, solution, source_ticket_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (device, problem, solution, source_ticket_id, created_at))

def db_update_knowledge_bite(bite_id: int, device: str, problem: str, solution: str):
    with get_conn() as con:
        con.execute("""
            UPDATE knowledge_bites
            SET device = ?, problem = ?, solution = ?
            WHERE id = ?
        """, (device, problem, solution, bite_id))

def db_delete_knowledge_bite(bite_id: int):
    with get_conn() as con:
        con.execute("DELETE FROM knowledge_bites WHERE id = ?", (bite_id,))

def db_get_knowledge_bite(bite_id: int):
    with get_conn() as con:
        row = con.execute("SELECT * FROM knowledge_bites WHERE id = ?", (bite_id,)).fetchone()
        return dict(row) if row else None

def db_sync_completed_tickets() -> int:
    # Check if tables exist before querying
    with get_conn() as con:
        t_row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'").fetchone()
        kb_row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_bites'").fetchone()
        if not t_row or not kb_row:
            return 0
            
    query = """
        SELECT id, device, issue, repair, notes, created 
        FROM tickets 
        WHERE status = 'Completed' 
          AND id NOT IN (
              SELECT source_ticket_id 
              FROM knowledge_bites 
              WHERE source_ticket_id IS NOT NULL
          )
    """
    with get_conn() as con:
        new_tickets = con.execute(query).fetchall()
        if not new_tickets:
            return 0
            
        synced_count = 0
        for t in new_tickets:
            # Safe date parsing with fallback
            raw_created = t["created"]
            parsed_date = _parse_date(raw_created)
            created_at = parsed_date.strftime("%Y-%m-%d") if parsed_date else datetime.date.today().strftime("%Y-%m-%d")
            
            # Query the repair log for a resolution or completion note
            log_query = """
                SELECT note FROM repair_log 
                WHERE ticket_id = ? AND status IN ('Resolution', 'Completed')
                ORDER BY id DESC LIMIT 1
            """
            log_row = con.execute(log_query, (t["id"],)).fetchone()
            if log_row and log_row["note"] and log_row["note"].strip():
                solution = log_row["note"].strip()
            else:
                repair = t["repair"] or ""
                solution = f"{repair} - {t['notes']}" if t["notes"] else repair
            
            try:
                cursor = con.execute("""
                    INSERT OR IGNORE INTO knowledge_bites (device, problem, solution, source_ticket_id, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (t["device"] or "Unknown Device", t["issue"] or "No description", solution, t["id"], created_at))
                if cursor.rowcount > 0:
                    synced_count += 1
            except Exception as e:
                logger.warning("Failed to sync ticket %s: %s", t['id'], e)
                
        con.commit()
        return synced_count
