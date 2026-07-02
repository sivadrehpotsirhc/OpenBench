"""
routers/finance.py
Finance and expense routes.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import io
import csv
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from plugins.finance.db import (
    db_all_expenses, db_insert_expense, db_update_expense,
    db_delete_expense, db_finance_summary, EXPENSE_CATEGORIES,
    db_get_expense
)

router = APIRouter()

class ExpenseCreate(BaseModel):
    date:        str
    description: Optional[str] = ""
    amount:      float = Field(..., gt=0)
    category:    str = "Other"
    source:      str = "Manual"
    notes:       Optional[str] = ""

    @field_validator('date')
    @classmethod
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        if v not in EXPENSE_CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(EXPENSE_CATEGORIES)}")
        return v

class FinanceSummary(BaseModel):
    repair_revenue:  float
    device_revenue:  float
    total_revenue:   float
    device_cost:     float
    expense_total:   float
    total_cost:      float
    net_profit:      float
    repair_count:    int
    device_count:    int

@router.get("/export")
def export_finance():
    expenses = db_all_expenses()
    if not expenses:
        raise HTTPException(status_code=404, detail="No expenses to export")
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=expenses[0].keys())
    writer.writeheader()
    writer.writerows(expenses)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses_export.csv"}
    )


@router.get("/summary", response_model=FinanceSummary)
def get_summary(frm: Optional[str] = None, to: Optional[str] = None):
    try:
        return db_finance_summary(frm, to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/expenses")
def list_expenses():
    return db_all_expenses()

@router.post("/expenses")
def create_expense(data: ExpenseCreate):
    db_insert_expense(data.dict())
    return {"created": True}

@router.put("/expenses/{expense_id}")
def update_expense(expense_id: int, data: ExpenseCreate):
    if not db_get_expense(expense_id):
        raise HTTPException(status_code=404, detail="Expense not found")
    db_update_expense({**data.dict(), "id": expense_id})
    return {"updated": expense_id}

@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    if not db_get_expense(expense_id):
        raise HTTPException(status_code=404, detail="Expense not found")
    db_delete_expense(expense_id)
    return {"deleted": expense_id}

@router.get("/categories")
def get_categories():
    return EXPENSE_CATEGORIES
