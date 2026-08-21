"""Public module catalogue endpoints; book ownership is enforced separately."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from dependencies.auth import get_current_user
from models.books import Module
from schemas.auth import UserResponse
from services.authorization import require_upload_permission

router = APIRouter(prefix="/api/v1/modules", tags=["modules"])
def _normal(value: str) -> str: return " ".join(value.lower().split())
def _item(row: Module) -> dict: return {"id": row.id, "name": row.name, "code": row.code, "description": row.description, "course_id": row.course_id}
class ModuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=255)
    code: Optional[str] = None
    description: Optional[str] = None
    course_id: Optional[int] = None

@router.get("")
async def list_modules(limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db), _user: UserResponse = Depends(get_current_user)):
    rows = (await db.execute(select(Module).order_by(Module.name).limit(limit))).scalars().all()
    return {"items": [_item(row) for row in rows], "total": len(rows)}
@router.get("/search")
async def search_modules(q: str = Query("", min_length=1), limit: int = Query(20, ge=1, le=50), db: AsyncSession = Depends(get_db), _user: UserResponse = Depends(get_current_user)):
    rows = (await db.execute(select(Module).where(Module.normalized_name.like(f"%{_normal(q)}%")).order_by(Module.name).limit(limit))).scalars().all()
    return {"items": [_item(row) for row in rows], "total": len(rows)}
@router.get("/{module_id}")
async def get_module(module_id: int, db: AsyncSession = Depends(get_db), _user: UserResponse = Depends(get_current_user)):
    row = await db.get(Module, module_id)
    if not row: raise HTTPException(404, "Module not found")
    return _item(row)
@router.post("", status_code=201)
async def create_module(payload: ModuleCreate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_upload_permission(actor)
    normalized = _normal(payload.name)
    row = (await db.execute(select(Module).where(Module.normalized_name == normalized))).scalar_one_or_none()
    if row: return {**_item(row), "existing": True}
    row = Module(name=" ".join(payload.name.split()), normalized_name=normalized, code=payload.code.strip().upper() if payload.code else None, description=payload.description, course_id=payload.course_id, created_by=str(actor.id))
    db.add(row); await db.commit(); await db.refresh(row)
    return {**_item(row), "existing": False}
