"""
routers/tickets.py
Full CRUD + stats + repair log routes for tickets.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import StreamingResponse
import io
import csv
import os
import uuid
import base64
import socket
import qrcode
from pydantic import BaseModel
from typing import Optional
from plugins.repair_tickets.db import (
    db_all_tickets, db_get_ticket, db_insert_ticket, db_update_ticket,
    db_delete_ticket, db_update_status, db_add_log, db_get_log,
    db_ticket_stats, gen_ticket_id, db_add_photo, db_get_photos, db_delete_photo
)
from plugins.repair_tickets.upload_sessions import create_session, get_session, clear_sessions_for_ticket
from core.customers import db_upsert_customer
from core.utils import add_biz_days, fmt_date
from core.constants import REPAIR_DAYS

router = APIRouter()

# ── Settings ──────────────────────────────────────────────────────────────────

from core.settings import get_setting, set_setting
import json

class SettingsUpdate(BaseModel):
    ticket_modules: Optional[str] = None
    ticket_repair_types: Optional[str] = None
    ticket_devices: Optional[str] = None
    ticket_techs: Optional[str] = None
    ticket_checklist: Optional[str] = None
    ticket_legal: Optional[str] = None

@router.get("/plugin_settings")
def get_plugin_settings():
    return {
        "ticket_modules": json.loads(get_setting("ticket_modules", "[]")),
        "ticket_repair_types": json.loads(get_setting("ticket_repair_types", "[]")),
        "ticket_devices": json.loads(get_setting("ticket_devices", "[]")),
        "ticket_techs": json.loads(get_setting("ticket_techs", "[]")),
        "ticket_checklist": json.loads(get_setting("ticket_checklist", "[]")),
        "ticket_legal": json.loads(get_setting("ticket_legal", "[]"))
    }

@router.post("/plugin_settings")
def update_plugin_settings(data: SettingsUpdate):
    if data.ticket_modules is not None:
        set_setting("ticket_modules", data.ticket_modules)
    if data.ticket_repair_types is not None:
        set_setting("ticket_repair_types", data.ticket_repair_types)
    if data.ticket_devices is not None:
        set_setting("ticket_devices", data.ticket_devices)
    if data.ticket_techs is not None:
        set_setting("ticket_techs", data.ticket_techs)
    if data.ticket_checklist is not None:
        set_setting("ticket_checklist", data.ticket_checklist)
    if data.ticket_legal is not None:
        set_setting("ticket_legal", data.ticket_legal)
    return {"status": "success"}



# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TicketCreate(BaseModel):
    priority:   str = "Standard"
    name:       str
    phone:      str
    email:      Optional[str] = ""
    address:    Optional[str] = ""
    device:     str
    serial:     Optional[str] = ""
    repair:     str
    price:      Optional[str] = ""
    issue:      Optional[str] = ""
    notes:      Optional[str] = ""
    technician: Optional[str] = ""
    due:        Optional[str] = None   # auto-calculated if omitted
    pre_repair_json: Optional[str] = "{}"
    tax_exempt:    bool = False
    discount_type: str = "None"
    custom_data:   Optional[str] = "{}"
    legal_json:    Optional[str] = "{}"


class TicketUpdate(BaseModel):
    priority:   Optional[str] = None
    name:       Optional[str] = None
    phone:      Optional[str] = None
    email:      Optional[str] = None
    address:    Optional[str] = None
    device:     Optional[str] = None
    serial:     Optional[str] = None
    repair:     Optional[str] = None
    price:      Optional[str] = None
    due:        Optional[str] = None
    issue:      Optional[str] = None
    notes:      Optional[str] = None
    status:     Optional[str] = None
    technician: Optional[str] = None
    pre_repair_json: Optional[str] = None
    tax_exempt:    Optional[bool] = None
    discount_type: Optional[str] = None
    custom_data:   Optional[str] = None
    legal_json:    Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


class LogEntry(BaseModel):
    status: str
    note:   str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/export")
def export_tickets():
    tickets = db_all_tickets()
    if not tickets:
        raise HTTPException(status_code=404, detail="No tickets to export")
    
    output = io.StringIO()
    # Handle the fact that SQLite rows might have different keys or be empty
    writer = csv.DictWriter(output, fieldnames=tickets[0].keys())
    writer.writeheader()
    writer.writerows(tickets)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets_export.csv"}
    )


@router.get("/stats")
def get_stats():
    return db_ticket_stats()


@router.get("/")
def list_tickets(status: str = None, search: str = None):
    return db_all_tickets(status=status, search=search)


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str):
    ticket = db_get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/")
def create_ticket(data: TicketCreate):
    from datetime import date
    ticket_id = gen_ticket_id()
    created   = date.today().strftime("%a, %b %d %Y")

    # Auto-calculate due date from repair type if not provided
    if data.due:
        due = data.due
    else:
        days = REPAIR_DAYS.get(data.repair)
        due  = fmt_date(add_biz_days(days)) if days else "—"

    ticket = {
        "id":         ticket_id,
        "priority":   data.priority,
        "name":       data.name,
        "phone":      data.phone,
        "email":      data.email,
        "address":    data.address,
        "device":     data.device,
        "serial":     data.serial,
        "repair":     data.repair,
        "price":      data.price,
        "due":        due,
        "created":    created,
        "issue":      data.issue,
        "notes":      data.notes,
        "status":     "Open",
        "technician": data.technician,
        "pre_repair_json": data.pre_repair_json,
        "tax_exempt": data.tax_exempt,
        "discount_type": data.discount_type,
        "cal_event_id": None,
        "custom_data": data.custom_data,
        "legal_json": data.legal_json,
    }
    db_insert_ticket(ticket)
    db_upsert_customer(ticket)
    return {"id": ticket_id, "ticket": ticket}


@router.put("/{ticket_id}")
def update_ticket(ticket_id: str, data: TicketUpdate):
    existing = db_get_ticket(ticket_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Ticket not found")
    updated = {**existing, **data.dict(exclude_unset=True)}
    db_update_ticket(updated)
    db_upsert_customer(updated)
    
    if updated.get("status") == "Completed":
        try:
            from plugins.knowledge_base.db import db_sync_completed_tickets
            db_sync_completed_tickets()
        except Exception as e:
            print("Failed to auto-sync knowledge base on ticket update:", e)
            
    return {"updated": ticket_id}


@router.patch("/{ticket_id}/status")
def update_status(ticket_id: str, body: StatusUpdate):
    if not db_get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    db_update_status(ticket_id, body.status)
    
    if body.status == "Completed":
        try:
            from plugins.knowledge_base.db import db_sync_completed_tickets
            db_sync_completed_tickets()
        except Exception as e:
            print("Failed to auto-sync knowledge base on status update:", e)
            
    return {"updated": ticket_id, "status": body.status}


@router.delete("/{ticket_id}")
def delete_ticket(ticket_id: str):
    if not db_get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    clear_sessions_for_ticket(ticket_id)
    db_delete_ticket(ticket_id)
    
    import shutil
    photo_dir = os.path.join("data", "ticket_photos", ticket_id)
    if os.path.exists(photo_dir):
        try:
            shutil.rmtree(photo_dir)
        except Exception as e:
            print(f"Error removing physical photo directory {photo_dir}: {e}")
            
    return {"deleted": ticket_id}


# ── Repair Log ────────────────────────────────────────────────────────────────

@router.get("/{ticket_id}/log")
def get_log(ticket_id: str):
    return db_get_log(ticket_id)


@router.post("/{ticket_id}/log")
def add_log(ticket_id: str, entry: LogEntry):
    if not db_get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    db_add_log(ticket_id, entry.status, entry.note)
    return {"logged": ticket_id}

# ── Photos ────────────────────────────────────────────────────────────────────

PHOTOS_DIR = os.path.join("data", "ticket_photos")

@router.get("/{ticket_id}/photos")
def get_photos(ticket_id: str):
    if not db_get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return db_get_photos(ticket_id)

@router.post("/{ticket_id}/photos")
def upload_desktop_photos(ticket_id: str, file: UploadFile = File(...)):
    if not db_get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket_dir = os.path.join(PHOTOS_DIR, ticket_id)
    os.makedirs(ticket_dir, exist_ok=True)
    
    safe_filename = os.path.basename(file.filename)
    filename = f"{uuid.uuid4()}_{safe_filename}"
    filepath = os.path.join(ticket_dir, filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(file.file.read())
        
    db_add_photo(str(uuid.uuid4()), ticket_id, filename, "desktop")
    return {"status": "success", "filename": filename}

@router.delete("/{ticket_id}/photos/{filename}")
def delete_photo(ticket_id: str, filename: str):
    if not db_get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(PHOTOS_DIR, ticket_id, safe_filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        
    db_delete_photo(ticket_id, safe_filename)
    return {"deleted": safe_filename}

# ── QR Upload Sessions ────────────────────────────────────────────────────────

def get_lan_ip():
    try:
        hostname = socket.gethostname()
        _, _, ips = socket.gethostbyname_ex(hostname)
        for ip in ips:
            if ip.startswith("192.168.") or ip.startswith("10."):
                return ip
            if ip.startswith("172."):
                parts = ip.split(".")
                if len(parts) >= 2:
                    try:
                        second = int(parts[1])
                        if 16 <= second <= 31:
                            return ip
                    except ValueError:
                        pass
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip != "127.0.0.1" and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip != "127.0.0.1" and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"

@router.post("/{ticket_id}/upload-session")
def create_upload_session(ticket_id: str, request: Request):
    if not db_get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    token = create_session(ticket_id)
    
    # Determine the base URL for the QR code
    port = request.url.port
    if not port:
        port = 8000 # fallback
        
    lan_ip = get_lan_ip()
    upload_url = f"{request.url.scheme}://{lan_ip}:{port}/photo-upload/{token}"
    
    # Generate QR Code image
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upload_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    qr_data_uri = f"data:image/png;base64,{img_str}"
    
    return {"token": token, "url": upload_url, "qr": qr_data_uri}

@router.get("/{ticket_id}/upload-session/{token}/status")
def check_session_status(ticket_id: str, token: str):
    session = get_session(token)
    if not session or session["ticket_id"] != ticket_id:
        return {"received": False, "count": 0}
    return {"received": session["received"], "count": session["count"]}



