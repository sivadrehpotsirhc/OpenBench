"""
routers/customers.py
Customer profile routes.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from core.customers import (
    db_all_customers, db_search_customers, db_get_customer_tickets,
    db_update_customer_notes, db_get_customer_stats
)

router = APIRouter()


class NotesUpdate(BaseModel):
    notes: str


@router.get("/")
def list_customers(search: str = None):
    if search:
        return db_search_customers(search)
    return db_all_customers()


@router.get("/{phone}/tickets")
def customer_tickets(phone: str):
    return db_get_customer_tickets(phone)


@router.get("/{phone}/stats")
def customer_stats(phone: str):
    return db_get_customer_stats(phone)


@router.patch("/{phone}/notes")
def update_notes(phone: str, body: NotesUpdate):
    db_update_customer_notes(phone, body.notes)
    return {"updated": phone}
