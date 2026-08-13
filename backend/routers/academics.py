from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services.academic_taxonomy import NODES, children, tree, validate_context
from services.programme_discovery import find_programme_matches, record_submission

router = APIRouter(prefix="/api/v1/academics", tags=["academics"])

@router.get("/taxonomy")
async def get_taxonomy(): return tree()

@router.get("/{parent_id}/children")
async def get_children(parent_id: str):
    if parent_id not in NODES: raise HTTPException(404, "Academic entity not found")
    return {"items": children(parent_id)}

class ProgrammeDiscoveryRequest(BaseModel):
    institution_id: str = "ur"
    campus_id: str
    college_id: str
    school_id: str
    programme_name_other: str = Field(min_length=1, max_length=180)

class ProgrammeSubmissionRequest(ProgrammeDiscoveryRequest):
    accepted_programme_id: Optional[str] = None
    accepted_candidate_id: Optional[int] = None
    source: Optional[str] = "profile"

@router.post("/programme-recommendations")
async def programme_recommendations(payload: ProgrammeDiscoveryRequest, db: AsyncSession = Depends(get_db)):
    try:
        validate_context(payload.institution_id, payload.campus_id, payload.college_id, payload.school_id, "other")
        recs = await find_programme_matches(db, institution_id=payload.institution_id, campus_id=payload.campus_id, college_id=payload.college_id, school_id=payload.school_id, raw_name=payload.programme_name_other)
        return {"recommendations": recs, "submission_candidate": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.post("/programme-submissions")
async def create_programme_submission(payload: ProgrammeSubmissionRequest, current_user: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        validate_context(payload.institution_id, payload.campus_id, payload.college_id, payload.school_id, "other")
        if payload.accepted_programme_id and payload.accepted_programme_id not in NODES:
            raise ValueError("Unknown recommended programme")
        row = await record_submission(db, user_id=str(current_user.id), institution_id=payload.institution_id, campus_id=payload.campus_id, college_id=payload.college_id, school_id=payload.school_id, raw_name=payload.programme_name_other, source=(payload.source or "profile"), accepted_programme_id=payload.accepted_programme_id, accepted_candidate_id=payload.accepted_candidate_id)
        await db.commit(); await db.refresh(row)
        return {"id": row.id, "status": row.status, "raw_programme_name": row.raw_programme_name}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
