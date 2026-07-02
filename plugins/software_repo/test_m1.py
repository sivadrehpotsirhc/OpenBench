import os
import sys
import sqlite3
import pytest

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Override DB_PATH to point to a temporary test database file
import core.db
TEST_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_software_repo.db"))
core.db.DB_PATH = TEST_DB_PATH

# Delete test db if exists
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass

# Mock the plugin manager before importing main to inject dummy routes
from core.plugin_loader import plugin_manager
original_load_all = plugin_manager.load_all

def mock_load_all():
    original_load_all()
    # Find the router for '/app/tools'
    for prefix, router in plugin_manager.routers:
        if prefix == "/app/tools":
            @router.get("/test-admin")
            def admin_test_endpoint():
                return {"status": "admin_ok"}

plugin_manager.load_all = mock_load_all

# Add a route to guest_router before main imports it
from plugins.software_repo.tools_guest import router as guest_router
@guest_router.get("/test-guest")
def guest_test_endpoint():
    return {"status": "guest_ok"}

# Now import main, which initializes the app and includes routers
import main
from main import app
from core.auth import get_current_user
from fastapi.testclient import TestClient

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown_db():
    # Explicitly run init_db for our plugin
    import plugins.software_repo.db as plugin_db
    plugin_db.init_db()
    yield
    # Clean up test database file
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

def test_db_schema_creation():
    # Verify that all 4 tables exist in the database and contain correct columns
    with core.db.get_conn() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        assert "tool_categories" in tables
        assert "tools" in tables
        assert "tool_sessions" in tables
        assert "tool_downloads" in tables

        # Verify tool_categories columns
        info = {row['name']: row for row in conn.execute("PRAGMA table_info(tool_categories)").fetchall()}
        assert "id" in info
        assert "name" in info
        assert "icon" in info
        assert "sort_order" in info

        # Verify tools columns
        info = {row['name']: row for row in conn.execute("PRAGMA table_info(tools)").fetchall()}
        assert "id" in info
        assert "category_id" in info
        assert "name" in info
        assert "filename" in info

def test_category_seeding_and_idempotency():
    expected_categories = [
        "Diagnostics",
        "Disk & Storage",
        "Cleaning",
        "Networking",
        "Browsers",
        "Media & PDF",
        "Security",
        "Utilities"
    ]
    
    with core.db.get_conn() as conn:
        cursor = conn.execute("SELECT name FROM tool_categories ORDER BY sort_order ASC;")
        categories = [row['name'] for row in cursor.fetchall()]
        assert categories == expected_categories

    # Re-run init_db to test idempotency
    import plugins.software_repo.db as plugin_db
    plugin_db.init_db()

    # Query again and check there are no duplicates
    with core.db.get_conn() as conn:
        cursor = conn.execute("SELECT name FROM tool_categories ORDER BY sort_order ASC;")
        categories = [row['name'] for row in cursor.fetchall()]
        assert categories == expected_categories

def test_foreign_key_constraints():
    # Verify that inserting a tool with non-existent category_id raises an IntegrityError
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        with core.db.get_conn() as conn:
            conn.execute("""
                INSERT INTO tools (category_id, name, filename)
                VALUES (9999, 'Test Tool Failed', 'failed_tool.exe')
            """)
    assert "FOREIGN KEY constraint failed" in str(exc_info.value)

def test_cascade_delete_category():
    # Verify that deleting a category sets its reference in tools to NULL
    with core.db.get_conn() as conn:
        # Insert a temporary category
        cursor = conn.execute("INSERT INTO tool_categories (name, icon) VALUES ('Temp Category', 'temp_icon')")
        cat_id = cursor.lastrowid
        
        # Insert a tool referencing this category
        cursor = conn.execute("""
            INSERT INTO tools (category_id, name, filename)
            VALUES (?, 'Temp Tool', 'temp_tool.exe')
        """, (cat_id,))
        tool_id = cursor.lastrowid
        
        # Verify tool is referenced correctly
        tool_row = conn.execute("SELECT category_id FROM tools WHERE id = ?", (tool_id,)).fetchone()
        assert tool_row['category_id'] == cat_id
        
        # Delete category
        conn.execute("DELETE FROM tool_categories WHERE id = ?", (cat_id,))
        
        # Verify tool category_id is set to NULL
        tool_row = conn.execute("SELECT category_id FROM tools WHERE id = ?", (tool_id,)).fetchone()
        assert tool_row['category_id'] is None

def test_routing_maps():
    client = TestClient(app)
    
    # Test guest route (unauthenticated)
    response = client.get("/tools/test-guest")
    assert response.status_code == 200
    assert response.json() == {"status": "guest_ok"}
    
    # Test admin route without auth (should be unauthorized 401)
    response = client.get("/app/tools/test-admin")
    assert response.status_code == 401
    
    # Test admin route with auth override
    app.dependency_overrides[get_current_user] = lambda: {"role": "technician"}
    try:
        response = client.get("/app/tools/test-admin")
        assert response.status_code == 200
        assert response.json() == {"status": "admin_ok"}
    finally:
        app.dependency_overrides.clear()

def test_tools_guest_import():
    import subprocess
    import sys
    # Verify tools_guest imports successfully (returncode == 0)
    res = subprocess.run([sys.executable, "-c", "import plugins.software_repo.tools_guest"], capture_output=True)
    assert res.returncode == 0
