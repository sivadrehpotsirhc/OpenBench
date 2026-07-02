"""
routers/inventory.py
Parts and vendor management routes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import sqlite3
from typing import Optional
from plugins.inventory.db import (
    db_all_parts, db_get_part, db_insert_part, db_update_part,
    db_delete_part, db_adjust_stock, db_search_parts, db_low_stock_parts,
    db_all_vendors, db_insert_vendor, db_update_vendor, db_delete_vendor,
    db_inventory_stats
)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class PartCreate(BaseModel):
    name:          str
    sku:           Optional[str] = ""
    category:      Optional[str] = ""
    qty:           int = Field(default=0, ge=0)
    reorder_point: int = Field(default=1, ge=0)
    cost:          Optional[float] = Field(default=None, ge=0)
    sell_price:    Optional[float] = Field(default=None, ge=0)
    vendor_id:     Optional[int] = None
    location:      Optional[str] = ""
    notes:         Optional[str] = ""


class StockAdjust(BaseModel):
    delta: int
    notes: Optional[str] = ""


class VendorCreate(BaseModel):
    name:    str
    contact: Optional[str] = ""
    phone:   Optional[str] = ""
    email:   Optional[str] = ""
    website: Optional[str] = ""
    notes:   Optional[str] = ""


# ── Parts ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats():
    return db_inventory_stats()


@router.get("/parts")
def list_parts(search: str = None, low_stock: bool = False):
    if low_stock:
        return db_low_stock_parts()
    if search:
        return db_search_parts(search)
    return db_all_parts()


@router.get("/parts/{part_id}")
def get_part(part_id: int):
    part = db_get_part(part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return part


@router.post("/parts")
def create_part(data: PartCreate):
    db_insert_part(data.dict())
    return {"created": True}


@router.put("/parts/{part_id}")
def update_part(part_id: int, data: PartCreate):
    if not db_get_part(part_id):
        raise HTTPException(status_code=404, detail="Part not found")
    db_update_part({**data.dict(), "id": part_id})
    return {"updated": part_id}


@router.patch("/parts/{part_id}/stock")
def adjust_stock(part_id: int, body: StockAdjust):
    if not db_get_part(part_id):
        raise HTTPException(status_code=404, detail="Part not found")
    db_adjust_stock(part_id, body.delta, body.notes)
    return {"adjusted": part_id, "delta": body.delta}


@router.delete("/parts/{part_id}")
def delete_part(part_id: int):
    if not db_get_part(part_id):
        raise HTTPException(status_code=404, detail="Part not found")
    try:
        db_delete_part(part_id)
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"Cannot delete part: it is referenced by existing records. Error: {str(e)}")
    return {"deleted": part_id}


# ── Vendors ───────────────────────────────────────────────────────────────────

@router.get("/vendors")
def list_vendors():
    return db_all_vendors()


@router.post("/vendors")
def create_vendor(data: VendorCreate):
    db_insert_vendor(data.dict())
    return {"created": True}


@router.put("/vendors/{vendor_id}")
def update_vendor(vendor_id: int, data: VendorCreate):
    db_update_vendor({**data.dict(), "id": vendor_id})
    return {"updated": vendor_id}


@router.delete("/vendors/{vendor_id}")
def delete_vendor(vendor_id: int):
    vendors = db_all_vendors()
    if not any(v["id"] == vendor_id for v in vendors):
        raise HTTPException(status_code=404, detail="Vendor not found")
    try:
        db_delete_vendor(vendor_id)
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"Cannot delete vendor: it is referenced by existing parts. Error: {str(e)}")
    return {"deleted": vendor_id}
