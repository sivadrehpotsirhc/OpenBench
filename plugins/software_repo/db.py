import os
import sqlite3
import datetime
from core.db import get_conn

def init_tools_tables():
    with get_conn() as con:
        # SQLite foreign key support is enabled
        con.execute("PRAGMA foreign_keys = ON;")
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS tool_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT,
                sort_order INTEGER DEFAULT 0
            )
        """)
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER REFERENCES tool_categories(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                description TEXT,
                version TEXT,
                filename TEXT NOT NULL UNIQUE,
                file_size_kb INTEGER,
                is_portable BOOLEAN DEFAULT 1,
                is_active BOOLEAN DEFAULT 1,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS tool_sessions (
                id TEXT PRIMARY KEY,
                pin_hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                revoked BOOLEAN DEFAULT 0,
                last_used DATETIME
            )
        """)
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS tool_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES tool_sessions(id) ON DELETE SET NULL,
                tool_id INTEGER REFERENCES tools(id) ON DELETE SET NULL,
                downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                client_ip TEXT
            )
        """)
        
        # Seed the 8 default categories in order
        categories = [
            ("Diagnostics", "", 1),
            ("Disk & Storage", "", 2),
            ("Cleaning", "", 3),
            ("Networking", "", 4),
            ("Browsers", "", 5),
            ("Media & PDF", "", 6),
            ("Security", "", 7),
            ("Utilities", "", 8)
        ]
        
        for name, icon, sort in categories:
            con.execute("""
                INSERT OR IGNORE INTO tool_categories (name, icon, sort_order)
                VALUES (?, ?, ?)
            """, (name, icon, sort))
            con.execute("""
                UPDATE tool_categories SET icon = ? WHERE name = ?
            """, (icon, name))

        # Cleanup duplicate emoji categories from previous runs
        emoji_map = {
            "🔬 Diagnostics": "Diagnostics",
            "💾 Disk & Storage": "Disk & Storage",
            "🧹 Cleaning": "Cleaning",
            "🌐 Networking": "Networking",
            "🌍 Browsers": "Browsers",
            "🎬 Media & PDF": "Media & PDF",
            "🔒 Security": "Security",
            "🔧 Utilities": "Utilities"
        }
        for emoji_name, clean_name in emoji_map.items():
            emoji_row = con.execute("SELECT id FROM tool_categories WHERE name = ?", (emoji_name,)).fetchone()
            clean_row = con.execute("SELECT id FROM tool_categories WHERE name = ?", (clean_name,)).fetchone()
            if emoji_row and clean_row:
                emoji_id = emoji_row["id"]
                clean_id = clean_row["id"]
                con.execute("UPDATE tools SET category_id = ? WHERE category_id = ?", (clean_id, emoji_id))
                con.execute("DELETE FROM tool_categories WHERE id = ?", (emoji_id,))
        
        # Cleanup any error message categories
        con.execute("DELETE FROM tool_categories WHERE name LIKE 'Error:%'")

def init_db():
    init_tools_tables()
    purge_expired_sessions()

def purge_expired_sessions():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        con.execute("DELETE FROM tool_sessions WHERE expires_at < ?", (now,))

def session_is_alive(token: str) -> bool:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        row = con.execute("""
            SELECT id FROM tool_sessions
            WHERE id = ? AND revoked = 0 AND expires_at > ?
        """, (token, now)).fetchone()
        return row is not None
