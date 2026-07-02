import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import core.db
from core.plugin_loader import plugin_manager
from routers import customers, invoices, calendar, settings

# check for plugins before loading web app
plugin_manager.load_all()

@asynccontextmanager
async def lifespan(app: FastAPI):
    core.db.init_db()
    plugin_manager.init_dbs()
    
    from services.backup_scheduler import start_scheduler
    await start_scheduler()
    
    yield

app = FastAPI(title="OpenBench", version="2.0.0", lifespan=lifespan)

@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    if os.environ.get("DEBUG", "0") == "1":
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "trace": traceback.format_exc()}
        )
    return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

from fastapi import Depends
from core.auth import get_current_user

# core api 
app.include_router(customers.router, prefix="/api/customers", tags=["Customers"], dependencies=[Depends(get_current_user)])
app.include_router(invoices.router,  prefix="/api/invoices",  tags=["Invoices"], dependencies=[Depends(get_current_user)])
app.include_router(calendar.router,  prefix="/api/calendar",  tags=["Calendar"], dependencies=[Depends(get_current_user)])
app.include_router(settings.router,  prefix="/api/settings",  tags=["Settings"]) # Settings router has mixed auth

# plugin routes
import logging
logger = logging.getLogger(__name__)

for prefix, router in plugin_manager.routers:
    try:
        app.include_router(router, prefix=prefix, tags=["Plugins"], dependencies=[Depends(get_current_user)])
    except Exception as e:
        logger.warning(f"Failed to register plugin router {prefix}: {e}")



# qrcode endpoint
import io
import qrcode
from fastapi.responses import StreamingResponse

@app.get("/api/qrcode")
def get_qrcode(data: str):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return StreamingResponse(img_byte_arr, media_type="image/png")

# static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# ticket photos
import os
os.makedirs(os.path.join("data", "ticket_photos"), exist_ok=True)
app.mount("/ticket-photos", StaticFiles(directory=os.path.join("data", "ticket_photos")), name="ticket_photos")

# unauthenticated photo upload routes
from plugins.repair_tickets.upload_sessions import get_session, mark_received
from plugins.repair_tickets.db import db_add_photo
import uuid
import shutil

@app.get("/photo-upload/{token}")
def serve_mobile_upload(token: str):
    path = os.path.join("plugins", "repair_tickets", "frontend", "mobile_upload.html")
    if os.path.exists(path) and os.path.isfile(path):
        return FileResponse(path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

@app.post("/photo-upload/{token}/submit")
def submit_mobile_photo(token: str, file: UploadFile = File(...)):
    session = get_session(token)
    if not session:
        return JSONResponse(status_code=403, content={"error": "Invalid or expired session"})
        
    ticket_id = session["ticket_id"]
    from plugins.repair_tickets.db import db_get_ticket
    if not db_get_ticket(ticket_id):
        return JSONResponse(status_code=404, content={"error": "Ticket does not exist in the database"})
        
    PHOTOS_DIR = os.path.join("data", "ticket_photos")
    ticket_dir = os.path.join(PHOTOS_DIR, ticket_id)
    os.makedirs(ticket_dir, exist_ok=True)
    
    safe_filename = os.path.basename(file.filename)
    filename = f"{uuid.uuid4()}_{safe_filename}"
    filepath = os.path.join(ticket_dir, filename)
    
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    db_add_photo(str(uuid.uuid4()), ticket_id, filename, "phone")
    mark_received(token)
    
    return {"status": "success", "filename": filename}


@app.get("/plugins/{plugin_id}/frontend/{filename}")
def serve_plugin_frontend(plugin_id: str, filename: str):
    if not all(c.isalnum() or c in '_-' for c in plugin_id):
        return JSONResponse(status_code=400, content={"error": "Invalid plugin ID"})
        
    plugins_dir = os.path.abspath("plugins")
    safe_filename = os.path.basename(filename)
    path = os.path.join(plugins_dir, plugin_id, "frontend", safe_filename)
    abs_path = os.path.abspath(path)
    
    if not abs_path.startswith(plugins_dir + os.sep):
        return JSONResponse(status_code=400, content={"error": "Invalid path traversal"})
        
    if os.path.exists(abs_path) and os.path.isfile(abs_path):
        return FileResponse(abs_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

try:
    from plugins.software_repo.tools_guest import router as guest_router
    app.include_router(guest_router, prefix="/tools", tags=["Guest Tools"])
except ImportError:
    pass

@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")
