from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from plugins.knowledge_base.db import (
    db_all_knowledge_bites, db_insert_knowledge_bite,
    db_update_knowledge_bite, db_delete_knowledge_bite,
    db_sync_completed_tickets,
    db_get_knowledge_bite
)

router = APIRouter()

class BiteCreate(BaseModel):
    device: str
    problem: str
    solution: str

class BiteUpdate(BaseModel):
    device: str
    problem: str
    solution: str

@router.get("/")
def get_bites(search: Optional[str] = None):
    return db_all_knowledge_bites(search=search)

@router.post("/sync")
def sync_bites():
    try:
        synced_count = db_sync_completed_tickets()
        return {"status": "success", "synced": synced_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync tickets: {str(e)}")

@router.post("/")
def create_bite(data: BiteCreate):
    try:
        db_insert_knowledge_bite(data.device, data.problem, data.solution)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{bite_id}")
def update_bite(bite_id: int, data: BiteUpdate):
    if not db_get_knowledge_bite(bite_id):
        raise HTTPException(status_code=404, detail="Knowledge bite not found")
    try:
        db_update_knowledge_bite(bite_id, data.device, data.problem, data.solution)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{bite_id}")
def delete_bite(bite_id: int):
    if not db_get_knowledge_bite(bite_id):
        raise HTTPException(status_code=404, detail="Knowledge bite not found")
    try:
        db_delete_knowledge_bite(bite_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
