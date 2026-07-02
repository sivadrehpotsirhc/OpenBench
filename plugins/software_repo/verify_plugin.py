import os
import sys
import tempfile
import pytest
import sqlite3
import datetime
import shutil
import threading
import uuid
import bcrypt

# Ensure OpenBench root is in sys.path
plugin_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(plugin_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Create a temporary database file
temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.close(temp_db_fd)

import config
config.DB_PATH = temp_db_path

# Pre-populate core and repair_tickets tables to satisfy other plugin dependencies during startup
from core.db import init_db as core_init_db
from plugins.repair_tickets.db import init_db as tickets_init_db
core_init_db()
tickets_init_db()

from main import app
from plugins.software_repo.db import init_tools_tables, get_conn
from fastapi.testclient import TestClient
from fastapi import Request, HTTPException
from core.auth import get_current_user

# Global toggle for admin mock authentication
admin_authenticated = True

def mock_get_current_user(request: Request):
    if not admin_authenticated:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"username": "admin", "role": "admin"}

app.dependency_overrides[get_current_user] = mock_get_current_user

@pytest.fixture(autouse=True)
def clean_db_and_library():
    # Setup: Initialize tables
    init_tools_tables()
    
    yield
    
    # Teardown: Clean up SQLite tables (drop and re-create to reset autoincrements)
    with get_conn() as con:
        con.execute("PRAGMA foreign_keys = OFF;")
        con.execute("DROP TABLE IF EXISTS tool_downloads;")
        con.execute("DROP TABLE IF EXISTS tool_sessions;")
        con.execute("DROP TABLE IF EXISTS tools;")
        con.execute("DROP TABLE IF EXISTS tool_categories;")
        con.execute("PRAGMA foreign_keys = ON;")
        
    # Clean up files in tools_library
    library_dir = os.path.join(plugin_dir, "tools_library")
    if os.path.exists(library_dir):
        for f in os.listdir(library_dir):
            fp = os.path.join(library_dir, f)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass

@pytest.fixture
def client():
    global admin_authenticated
    admin_authenticated = True
    with TestClient(app) as c:
        yield c

# ==============================================================================
# TIER 1: FEATURE COVERAGE (35 CASES)
# ==============================================================================

# --- Feature 1: DB Setup & Seeding ---

def test_tc_1_1_1_schema_creation_verification():
    with get_conn() as con:
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "tool_categories" in tables
    assert "tools" in tables
    assert "tool_sessions" in tables
    assert "tool_downloads" in tables

def test_tc_1_1_2_default_category_seeding():
    expected_categories = [
        "Diagnostics", "Disk & Storage", "Cleaning", "Networking",
        "Browsers", "Media & PDF", "Security", "Utilities"
    ]
    with get_conn() as con:
        rows = con.execute("SELECT name, sort_order FROM tool_categories ORDER BY sort_order ASC").fetchall()
    assert len(rows) == 8
    for idx, row in enumerate(rows):
        assert row["name"] == expected_categories[idx]
        assert row["sort_order"] == idx + 1

def test_tc_1_1_3_seeding_rerun_idempotency():
    init_tools_tables()
    with get_conn() as con:
        rows = con.execute("SELECT name FROM tool_categories ORDER BY sort_order ASC").fetchall()
    assert len(rows) == 8

def test_tc_1_1_4_primary_key_constraints():
    with get_conn() as con:
        meta = con.execute("PRAGMA table_info(tool_categories)").fetchall()
        id_col = [m for m in meta if m["name"] == "id"][0]
        assert id_col["pk"] == 1
        assert id_col["type"] == "INTEGER"

        session_meta = con.execute("PRAGMA table_info(tool_sessions)").fetchall()
        sid_col = [m for m in session_meta if m["name"] == "id"][0]
        assert sid_col["pk"] == 1
        assert sid_col["type"] == "TEXT"

def test_tc_1_1_5_foreign_key_constraints_check():
    with get_conn() as con:
        fk_list = con.execute("PRAGMA foreign_key_list(tools)").fetchall()
    assert len(fk_list) > 0
    cat_fk = [fk for fk in fk_list if fk["table"] == "tool_categories"][0]
    assert cat_fk["from"] == "category_id"
    assert cat_fk["to"] == "id"
    assert cat_fk["on_delete"] == "SET NULL"

# --- Feature 2: Admin Tool Management ---

def test_tc_1_2_1_add_tool_successful_upload(client):
    file_data = b"fake executable binary payload"
    files = {"file": ("test_tool.exe", file_data, "application/octet-stream")}
    data = {
        "name": "Diagnostic Tool",
        "description": "Diagnostic checks",
        "version": "1.0.2",
        "category_id": 1,
        "is_portable": "true"
    }
    response = client.post("/app/tools/tools/add", data=data, files=files)
    assert response.status_code == 200
    
    target_file = os.path.join(plugin_dir, "tools_library", "test_tool.exe")
    assert os.path.exists(target_file)
    
    with get_conn() as con:
        tool = con.execute("SELECT * FROM tools WHERE filename = 'test_tool.exe'").fetchone()
    assert tool is not None
    assert tool["name"] == "Diagnostic Tool"
    assert tool["is_active"] == 1

def test_tc_1_2_2_get_tools_sorted_list(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (2, 'B_tool', 'b.exe', 1)")
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Z_tool', 'z.exe', 1)")
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'A_tool', 'a.exe', 1)")

    response = client.get("/app/tools/tools")
    assert response.status_code == 200
    tools = response.json()
    assert len(tools) == 3
    assert tools[0]["name"] == "A_tool"
    assert tools[1]["name"] == "Z_tool"
    assert tools[2]["name"] == "B_tool"

def test_tc_1_2_3_toggle_tool_active_state(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Toggle Tool', 'toggle.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'toggle.exe'").fetchone()["id"]

    response = client.post(f"/app/tools/tools/{tool_id}/toggle")
    assert response.status_code == 200
    with get_conn() as con:
        assert con.execute("SELECT is_active FROM tools WHERE id = ?", (tool_id,)).fetchone()["is_active"] == 0

    response = client.post(f"/app/tools/tools/{tool_id}/toggle")
    assert response.status_code == 200
    with get_conn() as con:
        assert con.execute("SELECT is_active FROM tools WHERE id = ?", (tool_id,)).fetchone()["is_active"] == 1

def test_tc_1_2_4_delete_tool_success(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    file_path = os.path.join(library_dir, "delete.exe")
    with open(file_path, "wb") as f:
        f.write(b"deleteme")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Delete Tool', 'delete.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'delete.exe'").fetchone()["id"]

    response = client.delete(f"/app/tools/tools/{tool_id}")
    assert response.status_code == 200
    assert not os.path.exists(file_path)
    with get_conn() as con:
        assert con.execute("SELECT count(*) FROM tools WHERE id = ?", (tool_id,)).fetchone()[0] == 0

def test_tc_1_2_5_file_size_calculation(client):
    file_data = b"x" * 2048
    files = {"file": ("size_test.exe", file_data, "application/octet-stream")}
    data = {
        "name": "Size Tool",
        "category_id": 1,
        "is_portable": "true"
    }
    response = client.post("/app/tools/tools/add", data=data, files=files)
    assert response.status_code == 200
    with get_conn() as con:
        tool = con.execute("SELECT file_size_kb FROM tools WHERE filename = 'size_test.exe'").fetchone()
    assert tool["file_size_kb"] == 2

# --- Feature 3: Session Management ---

def test_tc_1_3_1_create_session_default_ttl(client):
    response = client.post("/app/tools/sessions/create")
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert len(data["pin"]) == 6
    assert data["ttl_minutes"] == 60

def test_tc_1_3_2_create_session_custom_ttl(client):
    response = client.post("/app/tools/sessions/create?ttl_minutes=120")
    assert response.status_code == 200
    data = response.json()
    assert data["ttl_minutes"] == 120
    exp = datetime.datetime.strptime(data["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = exp - now
    assert 118 < (diff.total_seconds() / 60) < 122

def test_tc_1_3_3_revoke_session(client):
    response = client.post("/app/tools/sessions/create")
    token = response.json()["token"]
    
    rev_resp = client.post(f"/app/tools/sessions/{token}/revoke")
    assert rev_resp.status_code == 200
    with get_conn() as con:
        row = con.execute("SELECT revoked FROM tool_sessions WHERE id = ?", (token,)).fetchone()
    assert row["revoked"] == 1

def test_tc_1_3_4_get_active_sessions(client):
    res = client.post("/app/tools/sessions/create")
    token_active = res.json()["token"]
    
    res2 = client.post("/app/tools/sessions/create")
    token_revoked = res2.json()["token"]
    client.post(f"/app/tools/sessions/{token_revoked}/revoke")

    expired_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        con.execute("""
            INSERT INTO tool_sessions (id, pin_hash, expires_at, revoked)
            VALUES (?, 'dummy', ?, 0)
        """, (str(uuid.uuid4()), expired_time))

    list_resp = client.get("/app/tools/sessions")
    assert list_resp.status_code == 200
    sessions = list_resp.json()
    tokens = [s["id"] for s in sessions]
    assert token_active in tokens
    assert token_revoked not in tokens

def test_tc_1_3_5_pin_hashing_verification(client):
    res = client.post("/app/tools/sessions/create")
    data = res.json()
    token = data["token"]
    pin = data["pin"]

    with get_conn() as con:
        row = con.execute("SELECT pin_hash FROM tool_sessions WHERE id = ?", (token,)).fetchone()
    assert row is not None
    assert row["pin_hash"] != pin
    assert bcrypt.checkpw(pin.encode('utf-8'), row["pin_hash"].encode('utf-8'))

# --- Feature 4: Guest Auth/Cookie ---

def test_tc_1_4_1_render_guest_login_page(client):
    response = client.get("/tools")
    assert response.status_code == 200
    assert "token" in response.text
    assert "PIN" in response.text

def test_tc_1_4_2_successful_guest_authentication(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    auth_resp = client.post("/tools/auth", data={"token": token, "pin": pin}, follow_redirects=False)
    assert auth_resp.status_code == 303
    assert auth_resp.headers["location"] == "/tools/library"
    assert "tools_session" in auth_resp.cookies

def test_tc_1_4_3_secure_cookie_properties(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    auth_resp = client.post("/tools/auth", data={"token": token, "pin": pin}, follow_redirects=False)
    cookie_hdr = auth_resp.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie_hdr
    assert "samesite=strict" in cookie_hdr.lower()
    assert "path=/tools" in cookie_hdr.lower()

def test_tc_1_4_4_failed_guest_authentication_incorrect_pin(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    
    auth_resp = client.post("/tools/auth", data={"token": token, "pin": "999999"}, follow_redirects=False)
    assert auth_resp.status_code == 401
    assert "tools_session" not in auth_resp.cookies
    assert "Invalid Token or PIN" in auth_resp.text

def test_tc_1_4_5_guest_logout(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    assert "tools_session" in client.cookies

    logout_resp = client.post("/tools/logout", follow_redirects=False)
    assert logout_resp.status_code == 303
    assert logout_resp.headers["location"] == "/tools"
    assert client.cookies.get("tools_session") in (None, "")

# --- Feature 5: Guest Library ---

def test_tc_1_5_1_access_library_authorized(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    lib_resp = client.get("/tools/library")
    assert lib_resp.status_code == 200
    assert "Library" in lib_resp.text

def test_tc_1_5_2_tool_grouping_by_category(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'DiagTool', 'diag.exe', 1)")
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (2, 'DiskTool', 'disk.exe', 1)")

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    lib_resp = client.get("/tools/library")
    assert lib_resp.status_code == 200
    assert "Diagnostics" in lib_resp.text
    assert "Disk &amp; Storage" in lib_resp.text or "Disk & Storage" in lib_resp.text

def test_tc_1_5_3_access_library_unauthorized_no_cookie(client):
    response = client.get("/tools/library", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tools"

def test_tc_1_5_4_access_library_unauthorized_invalid_cookie(client):
    client.cookies.set("tools_session", "invalid-token", path="/tools")
    response = client.get("/tools/library", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tools"

def test_tc_1_5_5_exclude_inactive_tools(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'ActiveTool', 'active.exe', 1)")
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'InactiveTool', 'inactive.exe', 0)")

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    lib_resp = client.get("/tools/library")
    assert "ActiveTool" in lib_resp.text
    assert "InactiveTool" not in lib_resp.text

# --- Feature 6: Guest Download ---

def test_tc_1_6_1_successful_tool_download(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "dl_test.exe"), "wb") as f:
        f.write(b"filecontents")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Download Tool', 'dl_test.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'dl_test.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    dl_resp = client.get(f"/tools/download/{tool_id}")
    assert dl_resp.status_code == 200
    assert dl_resp.content == b"filecontents"
    assert dl_resp.headers["content-type"] == "application/octet-stream"

def test_tc_1_6_2_download_session_validation(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "dl_test.exe"), "wb") as f:
        f.write(b"filecontents")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Download Tool', 'dl_test.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'dl_test.exe'").fetchone()["id"]

    client.cookies.set("tools_session", str(uuid.uuid4()), path="/tools")
    dl_resp = client.get(f"/tools/download/{tool_id}")
    assert dl_resp.status_code == 401

def test_tc_1_6_3_download_inactive_tool_rejected(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "inactive_dl.exe"), "wb") as f:
        f.write(b"inactive")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Inactive Tool', 'inactive_dl.exe', 0)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'inactive_dl.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    dl_resp = client.get(f"/tools/download/{tool_id}")
    assert dl_resp.status_code == 404

def test_tc_1_6_4_download_non_existent_tool_rejected(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    dl_resp = client.get("/tools/download/9999")
    assert dl_resp.status_code == 404

def test_tc_1_6_5_download_unauthorized_no_session(client):
    dl_resp = client.get("/tools/download/1")
    assert dl_resp.status_code == 401

# --- Feature 7: Audit Logging ---

def test_tc_1_7_1_download_logs_record_creation(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "audit.exe"), "wb") as f:
        f.write(b"data")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Audit Tool', 'audit.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'audit.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.get(f"/tools/download/{tool_id}")

    with get_conn() as con:
        log = con.execute("SELECT * FROM tool_downloads").fetchone()
    assert log is not None
    assert log["session_id"] == token
    assert log["tool_id"] == tool_id
    assert log["client_ip"] is not None

def test_tc_1_7_2_client_ip_capturing(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "ip.exe"), "wb") as f:
        f.write(b"ip")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'IP Tool', 'ip.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'ip.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.get(f"/tools/download/{tool_id}")

    with get_conn() as con:
        log = con.execute("SELECT client_ip FROM tool_downloads").fetchone()
    assert log["client_ip"] == "testclient"

def test_tc_1_7_3_admin_get_downloads_history(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'History Tool', 'hist.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'hist.exe'").fetchone()["id"]
        con.execute("INSERT INTO tool_sessions (id, pin_hash, expires_at) VALUES ('session-token', 'dummy', '2030-01-01 00:00:00')")
        con.execute("INSERT INTO tool_downloads (session_id, tool_id, client_ip) VALUES ('session-token', ?, '192.168.1.1')", (tool_id,))

    response = client.get("/app/tools/downloads")
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["tool_name"] == "History Tool"
    assert logs[0]["client_ip"] == "192.168.1.1"

def test_tc_1_7_4_join_with_tool_name(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'SpecialName', 'special.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'special.exe'").fetchone()["id"]
        con.execute("INSERT INTO tool_sessions (id, pin_hash, expires_at) VALUES ('session-token', 'dummy', '2030-01-01 00:00:00')")
        con.execute("INSERT INTO tool_downloads (session_id, tool_id, client_ip) VALUES ('session-token', ?, '192.168.1.1')", (tool_id,))

    response = client.get("/app/tools/downloads")
    logs = response.json()
    assert logs[0]["tool_name"] == "SpecialName"

def test_tc_1_7_5_chronological_order_of_logs(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'T1', 't1.exe', 1)")
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'T2', 't2.exe', 1)")
        con.execute("INSERT INTO tool_sessions (id, pin_hash, expires_at) VALUES ('s', 'd', '2030-01-01 00:00:00')")
        con.execute("INSERT INTO tool_downloads (session_id, tool_id, downloaded_at) VALUES ('s', 1, '2026-06-18 10:00:00')")
        con.execute("INSERT INTO tool_downloads (session_id, tool_id, downloaded_at) VALUES ('s', 2, '2026-06-18 10:05:00')")
        con.execute("INSERT INTO tool_downloads (session_id, tool_id, downloaded_at) VALUES ('s', 1, '2026-06-18 09:50:00')")

    response = client.get("/app/tools/downloads")
    logs = response.json()
    assert len(logs) == 3
    assert logs[0]["downloaded_at"] == "2026-06-18 10:05:00"
    assert logs[1]["downloaded_at"] == "2026-06-18 10:00:00"
    assert logs[2]["downloaded_at"] == "2026-06-18 09:50:00"

# ==============================================================================
# TIER 2: BOUNDARY & EDGE CASES (35 CASES)
# ==============================================================================

# --- Feature 1: DB Setup & Seeding ---

def test_tc_2_1_1_seed_category_unique_constraint():
    with get_conn() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO tool_categories (name) VALUES ('Diagnostics')")

def test_tc_2_1_2_tool_cascade_set_null():
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'C_Tool', 'c.exe', 1)")
        con.execute("DELETE FROM tool_categories WHERE id = 1")
        row = con.execute("SELECT category_id FROM tools WHERE filename = 'c.exe'").fetchone()
    assert row["category_id"] is None

def test_tc_2_1_3_missing_foreign_key_reference_insertion():
    with get_conn() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO tool_downloads (session_id, tool_id) VALUES ('non-existent', 1)")

def test_tc_2_1_4_empty_category_table_re_seeding():
    with get_conn() as con:
        con.execute("PRAGMA foreign_keys = OFF;")
        con.execute("DELETE FROM tool_categories")
        con.execute("PRAGMA foreign_keys = ON;")
    init_tools_tables()
    with get_conn() as con:
        count = con.execute("SELECT count(*) FROM tool_categories").fetchone()[0]
    assert count == 8

def test_tc_2_1_5_concurrent_db_initializations():
    errors = []
    def run_init():
        try:
            init_tools_tables()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=run_init) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0

# --- Feature 2: Admin Tool Management ---

def test_tc_2_2_1_delete_non_existent_tool(client):
    response = client.delete("/app/tools/tools/999")
    assert response.status_code == 404

def test_tc_2_2_2_add_tool_with_missing_fields(client):
    response = client.post("/app/tools/tools/add", data={"name": "Missing file"})
    assert response.status_code == 422

def test_tc_2_2_3_add_tool_filename_sanitization(client):
    file_data = b"sanitize"
    files = {"file": ("../../some/traversal/path.exe", file_data, "application/octet-stream")}
    data = {"name": "Sanitize", "category_id": 1}
    response = client.post("/app/tools/tools/add", data=data, files=files)
    assert response.status_code == 200
    
    target_file = os.path.join(plugin_dir, "tools_library", "path.exe")
    assert os.path.exists(target_file)
    with get_conn() as con:
        row = con.execute("SELECT filename FROM tools WHERE name='Sanitize'").fetchone()
    assert row["filename"] == "path.exe"

def test_tc_2_2_4_add_duplicate_filename_tool(client):
    file_data = b"utility"
    files = {"file": ("utility.exe", file_data, "application/octet-stream")}
    data = {"name": "Util1", "category_id": 1}
    client.post("/app/tools/tools/add", data=data, files=files)

    files2 = {"file": ("utility.exe", b"other", "application/octet-stream")}
    data2 = {"name": "Util2", "category_id": 1}
    response = client.post("/app/tools/tools/add", data=data2, files=files2)
    assert response.status_code == 400

def test_tc_2_2_5_toggle_non_existent_tool(client):
    response = client.post("/app/tools/tools/999/toggle")
    assert response.status_code == 404

# --- Feature 3: Session Management ---

def test_tc_2_3_1_expired_session_purging_on_create(client):
    expired_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        con.execute("""
            INSERT INTO tool_sessions (id, pin_hash, expires_at, revoked)
            VALUES ('expired-token', 'dummy', ?, 0)
        """, (expired_time,))

    response = client.post("/app/tools/sessions/create")
    assert response.status_code == 200
    with get_conn() as con:
        row = con.execute("SELECT count(*) FROM tool_sessions WHERE id='expired-token'").fetchone()[0]
    assert row == 0

def test_tc_2_3_2_revoke_already_revoked_session(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    
    client.post(f"/app/tools/sessions/{token}/revoke")
    response = client.post(f"/app/tools/sessions/{token}/revoke")
    assert response.status_code == 200
    with get_conn() as con:
        row = con.execute("SELECT revoked FROM tool_sessions WHERE id = ?", (token,)).fetchone()
    assert row["revoked"] == 1

def test_tc_2_3_3_revoke_non_existent_session(client):
    response = client.post("/app/tools/sessions/non-existent-uuid/revoke")
    assert response.status_code == 404

def test_tc_2_3_4_session_creation_with_negative_ttl(client):
    response = client.post("/app/tools/sessions/create?ttl_minutes=-10")
    assert response.status_code == 422

def test_tc_2_3_5_extremely_large_ttl(client):
    response = client.post("/app/tools/sessions/create?ttl_minutes=1000000")
    assert response.status_code == 200
    data = response.json()
    assert data["ttl_minutes"] == 1000000
    with get_conn() as con:
        row = con.execute("SELECT expires_at FROM tool_sessions WHERE id = ?", (data["token"],)).fetchone()
    assert row is not None

# --- Feature 4: Guest Auth/Cookie ---

def test_tc_2_4_1_auth_with_expired_session(client):
    expired_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    pin = "123456"
    pin_hash = bcrypt.hashpw(pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    token = str(uuid.uuid4())
    
    with get_conn() as con:
        con.execute("INSERT INTO tool_sessions (id, pin_hash, expires_at) VALUES (?, ?, ?)", (token, pin_hash, expired_time))

    response = client.post("/tools/auth", data={"token": token, "pin": pin})
    assert response.status_code == 401
    assert "tools_session" not in response.cookies
    assert "Invalid Token or PIN" in response.text

def test_tc_2_4_2_auth_with_revoked_session(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post(f"/app/tools/sessions/{token}/revoke")
    response = client.post("/tools/auth", data={"token": token, "pin": pin})
    assert response.status_code == 401
    assert "tools_session" not in response.cookies

def test_tc_2_4_3_generic_error_message_disclosure(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    
    resp1 = client.post("/tools/auth", data={"token": token, "pin": "999999"})
    resp2 = client.post("/tools/auth", data={"token": str(uuid.uuid4()), "pin": "123456"})
    
    assert resp1.status_code == 401
    assert resp2.status_code == 401
    assert resp1.text == resp2.text

def test_tc_2_4_4_session_last_used_update(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    with get_conn() as con:
        row = con.execute("SELECT last_used FROM tool_sessions WHERE id = ?", (token,)).fetchone()
    assert row["last_used"] is not None

def test_tc_2_4_5_auth_with_malformed_token_uuid(client):
    response = client.post("/tools/auth", data={"token": "' OR 1=1 --", "pin": "123456"})
    assert response.status_code == 401
    assert "tools_session" not in response.cookies
    assert "Invalid Token or PIN" in response.text

# --- Feature 5: Guest Library ---

def test_tc_2_5_1_access_library_with_expired_session_cookie(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    
    expired_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        con.execute("UPDATE tool_sessions SET expires_at = ? WHERE id = ?", (expired_time, token))

    response = client.get("/tools/library", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tools"

def test_tc_2_5_2_access_library_with_revoked_session_cookie(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    
    with get_conn() as con:
        con.execute("UPDATE tool_sessions SET revoked = 1 WHERE id = ?", (token,))

    response = client.get("/tools/library", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tools"

def test_tc_2_5_3_library_with_empty_active_tools_list(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    response = client.get("/tools/library")
    assert response.status_code == 200
    assert "No tools available" in response.text

def test_tc_2_5_4_access_library_with_modified_cookie_payload(client):
    client.cookies.set("tools_session", "valid-token' OR 1=1 --", path="/tools")
    response = client.get("/tools/library", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tools"

def test_tc_2_5_5_extremely_large_tool_library_render(client):
    with get_conn() as con:
        for idx in range(150):
            con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, ?, ?, 1)", (f"Tool_{idx}", f"t_{idx}.exe"))

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    response = client.get("/tools/library")
    assert response.status_code == 200
    assert "Tool_149" in response.text

# --- Feature 6: Guest Download ---

def test_tc_2_6_1_download_unauthorized_revoked_session(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    
    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.post(f"/app/tools/sessions/{token}/revoke")
    
    response = client.get("/tools/download/1")
    assert response.status_code == 401

def test_tc_2_6_2_download_unauthorized_expired_session(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    
    client.post("/tools/auth", data={"token": token, "pin": pin})
    
    expired = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        con.execute("UPDATE tool_sessions SET expires_at = ? WHERE id = ?", (expired, token))
        
    response = client.get("/tools/download/1")
    assert response.status_code == 401

def test_tc_2_6_3_safe_path_traversal_prevention(client):
    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})

    response = client.get("/tools/download/../../secret")
    assert response.status_code in (404, 400)

def test_tc_2_6_4_download_file_missing_on_disk(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Missing File', 'missing.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'missing.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})

    response = client.get(f"/tools/download/{tool_id}")
    assert response.status_code == 404

def test_tc_2_6_5_large_file_streaming_verification(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    file_path = os.path.join(library_dir, "large.exe")
    large_data = b"L" * 1024 * 1024
    with open(file_path, "wb") as f:
        f.write(large_data)

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Large', 'large.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'large.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})

    response = client.get(f"/tools/download/{tool_id}")
    assert response.status_code == 200
    assert response.content == large_data

# --- Feature 7: Audit Logging ---

def test_tc_2_7_1_delete_tool_cascade_behaviour(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "cas.exe"), "wb") as f:
        f.write(b"data")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Cas Tool', 'cas.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'cas.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.get(f"/tools/download/{tool_id}")

    client.delete(f"/app/tools/tools/{tool_id}")

    response = client.get("/app/tools/downloads")
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["tool_name"] is None

def test_tc_2_7_2_download_logs_pagination_limit(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'P', 'p.exe', 1)")
        con.execute("INSERT INTO tool_sessions (id, pin_hash, expires_at) VALUES ('session', 'dummy', '2030-01-01 00:00:00')")
        for _ in range(250):
            con.execute("INSERT INTO tool_downloads (session_id, tool_id) VALUES ('session', 1)")

    response = client.get("/app/tools/downloads")
    assert response.status_code == 200
    assert len(response.json()) == 200

def test_tc_2_7_3_localhost_client_ip_mapping(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "lh.exe"), "wb") as f:
        f.write(b"data")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Lh', 'lh.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'lh.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.get(f"/tools/download/{tool_id}")

    with get_conn() as con:
        row = con.execute("SELECT client_ip FROM tool_downloads").fetchone()
    assert row["client_ip"] in ("testclient", "127.0.0.1")

def test_tc_2_7_4_audit_logs_for_failed_downloads(client):
    client.cookies.set("tools_session", "invalid", path="/tools")
    client.get("/tools/download/1")
    
    with get_conn() as con:
        assert con.execute("SELECT count(*) FROM tool_downloads").fetchone()[0] == 0

def test_tc_2_7_5_session_revoked_cascade(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "rc.exe"), "wb") as f:
        f.write(b"data")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Rc', 'rc.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'rc.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.get(f"/tools/download/{tool_id}")

    client.post(f"/app/tools/sessions/{token}/revoke")

    response = client.get("/app/tools/downloads")
    assert len(response.json()) == 1

# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (7 CASES)
# ==============================================================================

def test_tc_3_1_1_live_revocation_interruption(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "live.exe"), "wb") as f:
        f.write(b"live")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Live', 'live.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'live.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.post(f"/app/tools/sessions/{token}/revoke")
    
    dl_resp = client.get(f"/tools/download/{tool_id}")
    assert dl_resp.status_code == 401

def test_tc_3_1_2_multi_client_session_isolation(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "t1.exe"), "wb") as f:
        f.write(b"t1")
    with open(os.path.join(library_dir, "t2.exe"), "wb") as f:
        f.write(b"t2")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'T1', 't1.exe', 1)")
        t1_id = con.execute("SELECT id FROM tools WHERE filename = 't1.exe'").fetchone()["id"]
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'T2', 't2.exe', 1)")
        t2_id = con.execute("SELECT id FROM tools WHERE filename = 't2.exe'").fetchone()["id"]

    res_a = client.post("/app/tools/sessions/create")
    token_a = res_a.json()["token"]
    pin_a = res_a.json()["pin"]

    res_b = client.post("/app/tools/sessions/create")
    token_b = res_b.json()["token"]
    pin_b = res_b.json()["pin"]

    client.post("/tools/auth", data={"token": token_a, "pin": pin_a})
    client.get(f"/tools/download/{t1_id}")

    client.post("/tools/auth", data={"token": token_b, "pin": pin_b})
    client.get(f"/tools/download/{t2_id}")

    with get_conn() as con:
        logs = con.execute("SELECT session_id, tool_id FROM tool_downloads ORDER BY id ASC").fetchall()
    assert len(logs) == 2
    assert logs[0]["session_id"] == token_a
    assert logs[0]["tool_id"] == t1_id
    assert logs[1]["session_id"] == token_b
    assert logs[1]["tool_id"] == t2_id

def test_tc_3_1_3_deactivation_during_active_session(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "deact.exe"), "wb") as f:
        f.write(b"data")

    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Deact', 'deact.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename = 'deact.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.post(f"/app/tools/tools/{tool_id}/toggle")
    
    response = client.get(f"/tools/download/{tool_id}")
    assert response.status_code == 404

def test_tc_3_1_4_cookie_overwrite_on_new_login(client):
    res_a = client.post("/app/tools/sessions/create")
    token_a = res_a.json()["token"]
    pin_a = res_a.json()["pin"]

    res_b = client.post("/app/tools/sessions/create")
    token_b = res_b.json()["token"]
    pin_b = res_b.json()["pin"]

    client.post("/tools/auth", data={"token": token_a, "pin": pin_a})
    assert client.cookies.get("tools_session") == token_a

    client.post("/tools/auth", data={"token": token_b, "pin": pin_b})
    assert client.cookies.get("tools_session") == token_b

def test_tc_3_1_5_purge_expired_sessions_and_active_audit_logs(client):
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'T', 't.exe', 1)")
        con.execute("INSERT INTO tool_sessions (id, pin_hash, expires_at) VALUES ('exp-session', 'hash', '2020-01-01 00:00:00')")
        con.execute("INSERT INTO tool_downloads (session_id, tool_id) VALUES ('exp-session', 1)")

    client.post("/app/tools/sessions/create")

    with get_conn() as con:
        assert con.execute("SELECT count(*) FROM tool_sessions WHERE id='exp-session'").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM tool_downloads WHERE session_id IS NULL").fetchone()[0] == 1

def test_tc_3_1_6_session_expiration_during_library_navigation(client):
    pin = "123456"
    pin_hash = bcrypt.hashpw(pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    token = str(uuid.uuid4())
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        con.execute("INSERT INTO tool_sessions (id, pin_hash, expires_at) VALUES (?, ?, ?)", (token, pin_hash, expires))

    client.post("/tools/auth", data={"token": token, "pin": pin})
    
    import time
    time.sleep(2)

    response = client.get("/tools/download/1")
    assert response.status_code == 401

def test_tc_3_1_7_reuploading_deleted_tool_and_downloading(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    
    files = {"file": ("test.exe", b"v1", "application/octet-stream")}
    data = {"name": "Test", "category_id": 1}
    res = client.post("/app/tools/tools/add", data=data, files=files)
    assert res.status_code == 200
    
    with get_conn() as con:
        t1_id = con.execute("SELECT id FROM tools WHERE filename='test.exe'").fetchone()["id"]

    res_s = client.post("/app/tools/sessions/create")
    token = res_s.json()["token"]
    pin = res_s.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})
    client.get(f"/tools/download/{t1_id}")

    client.delete(f"/app/tools/tools/{t1_id}")

    files2 = {"file": ("test.exe", b"v2", "application/octet-stream")}
    res2 = client.post("/app/tools/tools/add", data=data, files=files2)
    assert res2.status_code == 200
    
    with get_conn() as con:
        t2_id = con.execute("SELECT id FROM tools WHERE filename='test.exe'").fetchone()["id"]

    assert t1_id != t2_id

    dl = client.get(f"/tools/download/{t2_id}")
    assert dl.status_code == 200
    assert dl.content == b"v2"

# ==============================================================================
# TIER 4: REAL-WORLD SCENARIOS (5 CASES)
# ==============================================================================

def test_tc_4_1_1_standard_customer_device_setup_flow(client):
    res = client.post("/app/tools/sessions/create", data={"ttl_minutes": 30})
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    for name in ["t1.exe", "t2.exe", "t3.exe"]:
        with open(os.path.join(library_dir, name), "wb") as f:
            f.write(name.encode('utf-8'))
        with get_conn() as con:
            con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, ?, ?, 1)", (name, name))
            
    with get_conn() as con:
        tools = con.execute("SELECT id, name FROM tools").fetchall()

    for t in tools:
        res_dl = client.get(f"/tools/download/{t['id']}")
        assert res_dl.status_code == 200
        assert res_dl.content == t["name"].encode('utf-8')

    logs_resp = client.get("/app/tools/downloads")
    assert len(logs_resp.json()) == 3

def test_tc_4_1_2_hostile_client_boundary_probe(client):
    global admin_authenticated

    for _ in range(3):
        resp = client.post("/tools/auth", data={"token": str(uuid.uuid4()), "pin": "000000"})
        assert resp.status_code == 401
        assert "Invalid Token or PIN" in resp.text

    admin_authenticated = False
    try:
        resp_admin = client.get("/app/tools/tools")
        assert resp_admin.status_code == 401
    finally:
        admin_authenticated = True

    resp_trav = client.get("/tools/download/../../etc/passwd")
    assert resp_trav.status_code in (404, 401, 400)

def test_tc_4_1_3_midsession_support_revocation(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "tool.exe"), "wb") as f:
        f.write(b"code")
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Tool', 'tool.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename='tool.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]

    client.post("/tools/auth", data={"token": token, "pin": pin})
    
    lib = client.get("/tools/library")
    assert lib.status_code == 200

    client.post(f"/app/tools/sessions/{token}/revoke")

    dl = client.get(f"/tools/download/{tool_id}")
    assert dl.status_code == 401

def test_tc_4_1_4_database_maintenance_and_schema_upgrade_recovery(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "tool.exe"), "wb") as f:
        f.write(b"code")
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Tool', 'tool.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename='tool.exe'").fetchone()["id"]

    res = client.post("/app/tools/sessions/create")
    token = res.json()["token"]
    pin = res.json()["pin"]
    client.post("/tools/auth", data={"token": token, "pin": pin})

    init_tools_tables()

    dl = client.get(f"/tools/download/{tool_id}")
    assert dl.status_code == 200
    assert dl.content == b"code"

def test_tc_4_1_5_multiple_concurrent_guest_downloads(client):
    library_dir = os.path.join(plugin_dir, "tools_library")
    os.makedirs(library_dir, exist_ok=True)
    with open(os.path.join(library_dir, "tool.exe"), "wb") as f:
        f.write(b"data")
    with get_conn() as con:
        con.execute("INSERT INTO tools (category_id, name, filename, is_active) VALUES (1, 'Tool', 'tool.exe', 1)")
        tool_id = con.execute("SELECT id FROM tools WHERE filename='tool.exe'").fetchone()["id"]

    sessions = []
    for _ in range(10):
        res = client.post("/app/tools/sessions/create")
        sessions.append(res.json())

    errors = []
    def client_download(session):
        with TestClient(app) as local_client:
            try:
                local_client.post("/tools/auth", data={"token": session["token"], "pin": session["pin"]})
                dl_resp = local_client.get(f"/tools/download/{tool_id}")
                if dl_resp.status_code != 200 or dl_resp.content != b"data":
                    errors.append(f"Status: {dl_resp.status_code}, content: {dl_resp.content}")
            except Exception as e:
                errors.append(str(e))

    threads = [threading.Thread(target=client_download, args=(s,)) for s in sessions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    with get_conn() as con:
        count = con.execute("SELECT count(*) FROM tool_downloads").fetchone()[0]
    assert count == 10

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main(["-v", __file__]))
