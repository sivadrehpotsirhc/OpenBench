import os
import uuid
import shutil
import sqlite3
import datetime
import secrets
import bcrypt
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Request, Response
from pydantic import BaseModel
from core.db import get_conn
from plugins.software_repo.db import purge_expired_sessions

router = APIRouter()

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(PLUGIN_DIR, "tools_library")
os.makedirs(LIBRARY_DIR, exist_ok=True)

# --- Tool Management ---

@router.post("/tools/add")
def add_tool(
    name: str = Form(...),
    description: str = Form(None),
    version: str = Form(None),
    category_id: int = Form(...),
    is_portable: bool = Form(True),
    file: UploadFile = File(...)
):
    safe_filename = os.path.basename(file.filename)
    # Check duplicate filename in DB
    with get_conn() as con:
        row = con.execute("SELECT id FROM tools WHERE filename = ?", (safe_filename,)).fetchone()
        if row:
            raise HTTPException(status_code=400, detail="Tool with this filename already exists")

    MAX_FILE_SIZE = 50 * 1024 * 1024 # 50MB
    content_length = file.headers.get("content-length")
    size_to_check = MAX_FILE_SIZE
    if content_length:
        try:
            size_to_check = int(content_length)
        except ValueError:
            pass
            
    total, used, free = shutil.disk_usage(LIBRARY_DIR)
    if free < size_to_check:
        raise HTTPException(status_code=507, detail="Insufficient disk space")
        
    file_path = os.path.join(LIBRARY_DIR, safe_filename)
    try:
        bytes_written = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_FILE_SIZE:
                    f.close()
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(status_code=413, detail="File size exceeds maximum limit of 50MB")
                total, used, free = shutil.disk_usage(LIBRARY_DIR)
                if free < len(chunk):
                    f.close()
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(status_code=507, detail="Disk full during upload")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")

    file_size_bytes = os.path.getsize(file_path)
    file_size_kb = file_size_bytes // 1024

    try:
        with get_conn() as con:
            con.execute("""
                INSERT INTO tools (category_id, name, description, version, filename, file_size_kb, is_portable, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (category_id, name, description, version, safe_filename, file_size_kb, 1 if is_portable else 0))
    except Exception as e:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        if isinstance(e, sqlite3.IntegrityError):
            raise HTTPException(status_code=400, detail=f"Database integrity error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error during insertion: {str(e)}")

    return {"status": "success", "filename": safe_filename}

@router.post("/tools/{tool_id}/toggle")
def toggle_tool(tool_id: int):
    with get_conn() as con:
        row = con.execute("SELECT is_active FROM tools WHERE id = ?", (tool_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        new_state = 0 if row["is_active"] else 1
        con.execute("UPDATE tools SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_state, tool_id))
    return {"status": "success", "is_active": new_state}

@router.delete("/tools/{tool_id}")
def delete_tool(tool_id: int):
    filename = None
    with get_conn() as con:
        row = con.execute("SELECT filename FROM tools WHERE id = ?", (tool_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        filename = row["filename"]
        con.execute("DELETE FROM tools WHERE id = ?", (tool_id,))

    if filename:
        file_path = os.path.join(LIBRARY_DIR, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass # Safe deletion fallback

    return {"status": "success"}

@router.get("/tools")
def list_tools(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    with get_conn() as con:
        rows = con.execute("""
            SELECT t.id, t.category_id, t.name, t.description, t.version, t.filename, t.file_size_kb, t.is_portable, t.is_active,
                   c.name as category_name, c.icon as category_icon
            FROM tools t
            LEFT JOIN tool_categories c ON t.category_id = c.id
            ORDER BY c.sort_order ASC, t.name ASC
        """).fetchall()
        return [dict(r) for r in rows]

@router.get("/categories")
def list_categories(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    with get_conn() as con:
        rows = con.execute("SELECT id, name, icon, sort_order FROM tool_categories ORDER BY sort_order ASC").fetchall()
        return [dict(r) for r in rows]

# --- Session Management ---

@router.post("/sessions/create")
async def create_session(request: Request):
    purge_expired_sessions()

    ttl = 60
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = await request.json()
            if "ttl_minutes" in data:
                ttl_val = data["ttl_minutes"]
                if not isinstance(ttl_val, (int, float)):
                    raise HTTPException(status_code=422, detail="TTL must be an integer")
                ttl = int(ttl_val)
        except HTTPException:
            raise
        except Exception:
            pass
    else:
        # Form or Query params
        form = await request.form()
        if "ttl_minutes" in form:
            try:
                ttl = int(form["ttl_minutes"])
            except ValueError:
                raise HTTPException(status_code=422, detail="TTL must be an integer")
        elif "ttl_minutes" in request.query_params:
            try:
                ttl = int(request.query_params["ttl_minutes"])
            except ValueError:
                raise HTTPException(status_code=422, detail="TTL must be an integer")

    if ttl < 0:
        raise HTTPException(status_code=422, detail="TTL cannot be negative")

    # Generate 6 digit PIN using secrets.randbelow(10) x 6
    pin = "".join(str(secrets.randbelow(10)) for _ in range(6))
    token = str(uuid.uuid4())
    pin_hash = bcrypt.hashpw(pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    expires_at = (now_utc + datetime.timedelta(minutes=ttl)).strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as con:
        con.execute("""
            INSERT INTO tool_sessions (id, pin_hash, expires_at, revoked)
            VALUES (?, ?, ?, 0)
        """, (token, pin_hash, expires_at))

    return {
        "token": token,
        "pin": pin,
        "expires_at": expires_at,
        "ttl_minutes": ttl
    }

@router.post("/sessions/{token}/revoke")
def revoke_session(token: str):
    with get_conn() as con:
        row = con.execute("SELECT id FROM tool_sessions WHERE id = ?", (token,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        con.execute("UPDATE tool_sessions SET revoked = 1 WHERE id = ?", (token,))
    return {"status": "success"}

@router.get("/sessions")
def list_sessions(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        rows = con.execute("""
            SELECT id, created_at, expires_at, revoked, last_used
            FROM tool_sessions
            WHERE revoked = 0 AND expires_at > ?
            ORDER BY created_at DESC
        """, (now,)).fetchall()
        return [dict(r) for r in rows]

# --- Download History ---

@router.get("/downloads")
def list_downloads(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    with get_conn() as con:
        rows = con.execute("""
            SELECT td.id, td.session_id, td.tool_id, td.downloaded_at, td.client_ip, t.name as tool_name
            FROM tool_downloads td
            LEFT JOIN tools t ON td.tool_id = t.id
            ORDER BY td.downloaded_at DESC
            LIMIT 200
        """).fetchall()
        return [dict(r) for r in rows]
