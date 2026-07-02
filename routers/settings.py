"""
routers/settings.py
System settings and backup routes.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Request, Response, BackgroundTasks
from core.auth import get_current_user, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from services.backup_service import run_backup, list_backups, get_backup_dir, get_backup_info, restore_backup
import os
import shutil

router = APIRouter()

from core.settings import get_all_settings, set_settings
import core.constants as consts

@router.get("/constants", dependencies=[Depends(get_current_user)])
def get_constants():
    return {
        "STATUSES": consts.STATUSES,
        "STATUS_COLORS": consts.STATUS_COLORS,
        "REPAIR_DAYS": consts.REPAIR_DAYS,
        "REPAIR_PRICE": consts.REPAIR_PRICE,
        "REPAIR_TYPES": consts.REPAIR_TYPES,
        "DEVICE_TYPES": consts.DEVICE_TYPES,
        "PRIORITIES": consts.PRIORITIES,
        "PART_CATEGORIES": consts.PART_CATEGORIES,
        "DEVICE_CONDITIONS": consts.DEVICE_CONDITIONS,
        "DEVICE_STATUSES": consts.DEVICE_STATUSES,
    }

from core.plugin_loader import plugin_manager

@router.get("/plugins", dependencies=[Depends(get_current_user)])
def get_plugins():
    # Return the metadata for all active plugins
    return list(plugin_manager.plugins.values())

from pydantic import BaseModel, field_validator
from typing import Optional

class ConfigUpdate(BaseModel):
    tax_rate: Optional[str] = None
    tax_label: Optional[str] = None
    currency_symbol: Optional[str] = None
    shop_name: Optional[str] = None
    shop_tagline: Optional[str] = None
    shop_phone: Optional[str] = None
    shop_email: Optional[str] = None
    shop_address: Optional[str] = None
    ticket_modules: Optional[str] = None
    ticket_repair_types: Optional[str] = None
    ticket_devices: Optional[str] = None
    ticket_techs: Optional[str] = None
    ticket_checklist: Optional[str] = None
    ticket_legal: Optional[str] = None
    invoice_footer: Optional[str] = None
    email_templates: Optional[str] = None
    backup_frequency: Optional[str] = None
    backup_retention_days: Optional[str] = None
    backup_directory: Optional[str] = None
    timezone: Optional[str] = None
    time_format: Optional[str] = None
    display_density: Optional[str] = None

    @field_validator("tax_rate")
    @classmethod
    def validate_tax_rate(cls, v):
        if v is not None:
            try:
                val = float(v)
            except ValueError:
                raise ValueError("tax_rate must be a valid floating-point number")
            if val < 0 or val > 100:
                raise ValueError("tax_rate must be between 0 and 100")
        return v

    @field_validator("backup_retention_days")
    @classmethod
    def validate_retention_days(cls, v):
        if v is not None:
            try:
                val = int(v)
            except ValueError:
                raise ValueError("backup_retention_days must be a valid integer")
            if val <= 0:
                raise ValueError("backup_retention_days must be greater than 0")
        return v

    @field_validator("backup_frequency")
    @classmethod
    def validate_backup_frequency(cls, v):
        if v is not None:
            allowed = {"off", "every 6 hours", "every 12 hours", "daily", "weekly"}
            if v.strip().lower() not in allowed:
                raise ValueError(f"backup_frequency must be one of {allowed}")
        return v

@router.get("/config", dependencies=[Depends(get_current_user)])
def get_config():
    return get_all_settings()

@router.post("/config", dependencies=[Depends(get_current_user)])
def update_config(data: ConfigUpdate):
    set_settings(data.dict(exclude_unset=True))
    return {"updated": True}

@router.get("/backups", dependencies=[Depends(get_current_user)])
def get_backups():
    return list_backups()

@router.get("/backups/info", dependencies=[Depends(get_current_user)])
def get_backups_info():
    return get_backup_info()

@router.post("/backups", dependencies=[Depends(get_current_user)])
def create_backup():
    path = run_backup()
    if not path:
        raise HTTPException(status_code=500, detail="Backup failed")
    return {"created": True, "filename": os.path.basename(path)}

@router.post("/backups/restore", dependencies=[Depends(get_current_user)])
def restore_backup_route(file: UploadFile = File(...)):
    if not file.filename.endswith('.zip'):
        return JSONResponse(status_code=400, content={"error": "Must be a zip file"})
        
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
        
    success = restore_backup(tmp_path)
    os.remove(tmp_path)
    
    if success:
        return {"success": True, "message": "Database restored successfully."}
    return JSONResponse(status_code=500, content={"error": "Restore failed."})

@router.get("/backups/download/{filename}", dependencies=[Depends(get_current_user)])
def download_backup(filename: str):
    import os
    safe_filename = os.path.basename(filename)
    path = os.path.join(get_backup_dir(), safe_filename)
    if os.path.exists(path):
        return FileResponse(path, filename=safe_filename)
    return JSONResponse(status_code=404, content={"error": "Backup not found"})



@router.get("/auth/status")
def auth_status(request: Request):
    from core.db import get_conn
    from core.auth import ACTIVE_TOKENS
    from core.settings import get_setting
    
    # Check if we need to migrate from master_pin to pins table
    master_pin = get_setting('master_pin')
    
    with get_conn() as con:
        pins_count = con.execute("SELECT COUNT(*) FROM pins").fetchone()[0]
        
        if pins_count == 0 and master_pin:
            # Auto-migrate
            con.execute("INSERT INTO pins (label, pin_hash, role) VALUES (?, ?, ?)", ("Owner", master_pin, "owner"))
            pins_count = 1
            
    has_pin = pins_count > 0
    
    token = request.cookies.get("auth_token")
    is_authed = token in ACTIVE_TOKENS
    user = ACTIVE_TOKENS.get(token) if is_authed else None
    
    # If there is no PIN set, they are technically unauthed but we must force them to set it
    if not has_pin:
        is_authed = False

    shop_name = get_setting('shop_name') or 'OpenBench'

    return {"has_pin": has_pin, "is_authed": is_authed, "user": user, "shop_name": shop_name}


@router.post("/auth/login")
async def auth_login(request: Request, response: Response):
    from core.db import get_conn
    from core.auth import ACTIVE_TOKENS, hash_pin, verify_pin
    import secrets
    from datetime import datetime
    
    data = await request.json()
    pin = data.get("pin")
    label = data.get("label") # For first time setup
    
    if not pin or len(pin) != 6:
        return JSONResponse(status_code=400, content={"error": "Invalid PIN format"})
        
    with get_conn() as con:
        pins_count = con.execute("SELECT COUNT(*) FROM pins").fetchone()[0]
        
        # First time setup
        if pins_count == 0:
            if not label:
                return JSONResponse(status_code=400, content={"error": "Label is required for first-time setup"})
            hashed_pin = hash_pin(pin)
            con.execute("INSERT INTO pins (label, pin_hash, role, created) VALUES (?, ?, ?, ?)", 
                        (label, hashed_pin, "owner", datetime.now().isoformat()))
            user_data = {"name": label, "role": "owner"}
        else:
            # Verify
            rows = con.execute("SELECT id, label, pin_hash, role FROM pins").fetchall()
            matched_row = None
            for r in rows:
                if verify_pin(pin, r["pin_hash"]):
                    matched_row = r
                    break
            if not matched_row:
                return JSONResponse(status_code=401, content={"error": "Invalid PIN"})
            user_data = {"name": matched_row["label"], "role": matched_row["role"]}
            
            # Upgrade legacy SHA-256 hash to bcrypt upon next login
            stored_hash = matched_row["pin_hash"]
            is_legacy = len(stored_hash) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored_hash)
            if is_legacy:
                con.execute("UPDATE pins SET pin_hash=? WHERE id=?", (hash_pin(pin), matched_row["id"]))
            
    # Success
    token = secrets.token_urlsafe(32)
    ACTIVE_TOKENS[token] = user_data
    
    resp = JSONResponse(content={"success": True, "user": user_data})
    resp.set_cookie(key="auth_token", value=token, httponly=True, samesite="lax")
    return resp

@router.post("/auth/logout")
def auth_logout(request: Request, response: Response):
    from core.auth import ACTIVE_TOKENS
    token = request.cookies.get("auth_token")
    if token in ACTIVE_TOKENS:
        del ACTIVE_TOKENS[token]
        
    resp = JSONResponse(content={"success": True})
    resp.delete_cookie("auth_token")
    return resp

@router.get("/auth/pins")
def get_pins(user: dict = Depends(get_current_user)):
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    from core.db import get_conn
    with get_conn() as con:
        rows = con.execute("SELECT id, label, role, created FROM pins").fetchall()
        return [dict(r) for r in rows]

@router.post("/auth/pins")
async def add_pin(request: Request, user: dict = Depends(get_current_user)):
    from core.auth import hash_pin
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    data = await request.json()
    pin = data.get("pin")
    label = data.get("label")
    role = data.get("role", "technician")
    
    if not pin or len(pin) != 6 or not label:
        return JSONResponse(status_code=400, content={"error": "Invalid data"})
        
    from core.db import get_conn
    from datetime import datetime
    with get_conn() as con:
        con.execute("INSERT INTO pins (label, pin_hash, role, created) VALUES (?, ?, ?, ?)", 
                    (label, hash_pin(pin), role, datetime.now().isoformat()))
    return {"success": True}

@router.delete("/auth/pins/{pin_id}")
def delete_pin(pin_id: int, user: dict = Depends(get_current_user)):
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    from core.db import get_conn
    with get_conn() as con:
        count = con.execute("SELECT COUNT(*) FROM pins").fetchone()[0]
        if count <= 1:
            return JSONResponse(status_code=400, content={"error": "Cannot delete the last PIN"})
        con.execute("DELETE FROM pins WHERE id=?", (pin_id,))
    return {"success": True}

@router.put("/auth/pins/{pin_id}")
async def update_pin(pin_id: int, request: Request, user: dict = Depends(get_current_user)):
    from core.auth import hash_pin
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    data = await request.json()
    label = data.get("label")
    role = data.get("role")
    pin = data.get("pin")
    
    from core.db import get_conn
    with get_conn() as con:
        if pin and len(pin) == 6:
            con.execute("UPDATE pins SET label=?, role=?, pin_hash=? WHERE id=?", (label, role, hash_pin(pin), pin_id))
        else:
            con.execute("UPDATE pins SET label=?, role=? WHERE id=?", (label, role, pin_id))
    return {"success": True}

from services.export_service import export_all_data, export_module

@router.get("/export/all", dependencies=[Depends(get_current_user)])
def export_all(background_tasks: BackgroundTasks):
    zip_path = export_all_data()
    if not zip_path:
        return JSONResponse(status_code=500, content={"error": "Export failed"})
    background_tasks.add_task(os.remove, zip_path)
    return FileResponse(zip_path, filename=os.path.basename(zip_path))

@router.get("/export/{module}", dependencies=[Depends(get_current_user)])
def export_single_module(module: str, background_tasks: BackgroundTasks):
    csv_path = export_module(module)
    if not csv_path:
        return JSONResponse(status_code=404, content={"error": "Module not found or empty"})
    background_tasks.add_task(os.remove, csv_path)
    return FileResponse(csv_path, filename=os.path.basename(csv_path))

from services.reset_service import reset_all_data, reset_module

@router.post("/danger/reset-all")
async def danger_reset_all(request: Request, user: dict = Depends(get_current_user)):
    from core.auth import ACTIVE_TOKENS
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    data = await request.json()
    if data.get("confirmation") != "DELETE EVERYTHING":
        return JSONResponse(status_code=400, content={"error": "Invalid confirmation text"})
        
    reset_all_data()
    
    # Clear all sessions
    ACTIVE_TOKENS.clear()
    
    return {"success": True}

@router.post("/danger/reset-module")
async def danger_reset_module(request: Request, user: dict = Depends(get_current_user)):
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    data = await request.json()
    if data.get("confirmation") != "DELETE":
        return JSONResponse(status_code=400, content={"error": "Invalid confirmation text"})
        
    module = data.get("module")
    if reset_module(module):
        return {"success": True}
    return JSONResponse(status_code=400, content={"error": "Invalid module"})

@router.get("/system-info", dependencies=[Depends(get_current_user)])
def get_system_info():
    import sys
    from config import DB_PATH
    
    db_size = 0
    if os.path.exists(DB_PATH):
        db_size = os.path.getsize(DB_PATH)
        
    from core.db import get_conn
    counts = {}
    with get_conn() as con:
        tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        
        SAFE_TABLES = {"tickets", "repair_log", "parts", "vendors", "devices", "customers", "expenses", "transactions", "pins", "settings"}
        
        for t in tables:
            try:
                if t['name'] in SAFE_TABLES:
                    counts[t['name']] = con.execute(f"SELECT COUNT(*) FROM {t['name']}").fetchone()[0]
            except:
                pass
                
    return {
        "version": "2.0.0",
        "python_version": sys.version,
        "db_size": db_size,
        "table_counts": counts
    }

@router.get("/sessions")
def get_sessions(request: Request, user: dict = Depends(get_current_user)):
    from core.auth import ACTIVE_TOKENS
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    # We just return the number of active tokens
    return {"active_sessions": len(ACTIVE_TOKENS)}

@router.post("/sessions/revoke-others")
def revoke_other_sessions(request: Request, user: dict = Depends(get_current_user)):
    from core.auth import ACTIVE_TOKENS
    if user.get("role") != "owner":
        return JSONResponse(status_code=403, content={"error": "Owner access required"})
        
    current_token = request.cookies.get("auth_token")
    to_remove = [k for k in ACTIVE_TOKENS.keys() if k != current_token]
    for k in to_remove:
        del ACTIVE_TOKENS[k]
        
    return {"success": True, "revoked": len(to_remove)}
