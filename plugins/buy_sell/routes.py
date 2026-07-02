"""
routers/buysell.py
Buy/sell device routes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
from plugins.buy_sell.db import (
    db_all_devices, db_get_device, db_insert_device,
    db_update_device, db_delete_device, db_buysell_stats
)

router = APIRouter()


class DeviceCreate(BaseModel):
    customer_name:  Optional[str] = ""
    customer_phone: Optional[str] = ""
    device:         str
    condition:      str = "Good"
    purchase_price: Optional[float] = None
    sell_price:     Optional[float] = None
    status:         Literal["Staging", "Ready for Sale", "Sold"] = "Staging"
    notes:          Optional[str] = ""
    date_sold:      Optional[str] = ""


class DeviceUpdate(DeviceCreate):
    pass


@router.get("/stats")
def get_stats():
    return db_buysell_stats()


@router.get("/")
def list_devices(status: str = None, search: str = None):
    return db_all_devices(status=status, search=search)


@router.get("/{device_id}")
def get_device(device_id: int):
    device = db_get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("/")
def create_device(data: DeviceCreate):
    db_insert_device(data.dict())
    return {"created": True}


@router.put("/{device_id}")
def update_device(device_id: int, data: DeviceUpdate):
    current = db_get_device(device_id)
    if not current:
        raise HTTPException(status_code=404, detail="Device not found")
    if current.get("status") == "Sold":
        if (data.status != current.get("status") or
            data.purchase_price != current.get("purchase_price") or
            data.sell_price != current.get("sell_price")):
            raise HTTPException(status_code=400, detail="Cannot modify status, price, or cost on a device that is already Sold")
    db_update_device({**data.dict(), "id": device_id})
    return {"updated": device_id}


@router.delete("/{device_id}")
def delete_device(device_id: int):
    if not db_get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    db_delete_device(device_id)
    return {"deleted": device_id}
