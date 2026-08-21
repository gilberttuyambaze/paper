"""Reusable academic course catalogue for book relationships and future uploads."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.courses import Course
from schemas.auth import UserResponse
from services.authorization import require_upload_permission

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])

def _normal(value: str) -> str: return " ".join(value.strip().lower().split())
def _code(value: str | None) -> str | None: return "".join((value or "").upper().split()) or None
def _item(row: Course) -> dict: return {"id": row.id, "code": row.code, "name": row.name, "description": row.description}

class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=255)
    code: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None

@router.get("")
async def list_courses(limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db), _user: UserResponse = Depends(get_current_user)):
    rows = (await db.execute(select(Course).where(Course.deleted_at.is_(None)).order_by(Course.name).limit(limit))).scalars().all()
    return {"items": [_item(row) for row in rows], "total": len(rows)}

@router.get("/search")
async def search_courses(q: str = Query("", min_length=1), limit: int = Query(20, ge=1, le=50), db: AsyncSession = Depends(get_db), _user: UserResponse = Depends(get_current_user)):
    text, code = _normal(q), _code(q)
    rows = (await db.execute(select(Course).where(Course.deleted_at.is_(None), or_(Course.normalized_name.like(f"%{text}%"), Course.normalized_code.like(f"%{code or text}%"))).order_by(Course.name).limit(limit))).scalars().all()
    return {"items": [_item(row) for row in rows], "total": len(rows)}

@router.get("/{course_id}")
async def get_course(course_id: int, db: AsyncSession = Depends(get_db), _user: UserResponse = Depends(get_current_user)):
    course = await db.get(Course, course_id)
    if not course or course.deleted_at: raise HTTPException(404, "Course not found")
    return _item(course)

@router.post("", status_code=201)
async def create_course(payload: CourseCreate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_upload_permission(actor)
    name, code = " ".join(payload.name.split()), _code(payload.code)
    existing = (await db.execute(select(Course).where(Course.normalized_code == code))).scalar_one_or_none() if code else None
    existing = existing or (await db.execute(select(Course).where(Course.normalized_name == _normal(name)))).scalar_one_or_none()
    if existing: return {**_item(existing), "existing": True}
    course = Course(name=name, normalized_name=_normal(name), code=code, normalized_code=code, description=payload.description, created_by=str(actor.id))
    db.add(course); await db.commit(); await db.refresh(course)
    return {**_item(course), "existing": False}
