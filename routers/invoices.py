"""
routers/invoices.py
Invoice generation endpoint — fetches ticket from DB and returns a PDF download.
"""
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from plugins.repair_tickets.db import db_get_ticket
from services.invoice_service import generate_invoice

router = APIRouter()


@router.post("/{ticket_id}")
def create_invoice(ticket_id: str, background_tasks: BackgroundTasks):
    ticket = db_get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    pdf_path = generate_invoice(ticket)
    background_tasks.add_task(os.remove, pdf_path)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"invoice_{ticket_id}.pdf"
    )
