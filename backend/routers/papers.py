import json
import logging
from pathlib import Path
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.user_profiles import User_profiles
from services.papers import PapersService
from services.passage_indexing import PassageIndexService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services.authorization import require_upload_permission
from services.authorization import require_paper_management
from models.papers import Papers

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/papers", tags=["papers"])
MOCK_PAPERS_PATH = Path(__file__).resolve().parent.parent / "mock_data" / "papers.json"


# ---------- Pydantic Schemas ----------
class PapersData(BaseModel):
    """Entity data schema (for create/update)"""
    title: str
    course_code: str
    course_name: str
    college: str
    department: str
    year: int
    paper_type: str
    lecturer: str = None
    description: str = None
    file_key: str = None
    solution_key: str = None
    verification_status: str
    download_count: int = None
    report_count: int = None
    is_hidden: bool = None
    created_at: Optional[datetime] = None


class PapersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    title: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    college: Optional[str] = None
    department: Optional[str] = None
    year: Optional[int] = None
    paper_type: Optional[str] = None
    lecturer: Optional[str] = None
    description: Optional[str] = None
    file_key: Optional[str] = None
    solution_key: Optional[str] = None
    verification_status: Optional[str] = None
    download_count: Optional[int] = None
    report_count: Optional[int] = None
    is_hidden: Optional[bool] = None
    created_at: Optional[datetime] = None


class PapersResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    title: str
    course_code: str
    course_name: str
    college: str
    department: str
    year: int
    paper_type: str
    lecturer: Optional[str] = None
    description: Optional[str] = None
    file_key: Optional[str] = None
    solution_key: Optional[str] = None
    verification_status: str
    download_count: Optional[int] = None
    report_count: Optional[int] = None
    is_hidden: Optional[bool] = None
    created_at: Optional[datetime] = None
    uploader_display_name: Optional[str] = None
    uploader_profile_picture_key: Optional[str] = None

    class Config:
        from_attributes = True


class PapersListResponse(BaseModel):
    """List response schema"""
    items: List[PapersResponse]
    total: int
    skip: int
    limit: int


class PapersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[PapersData]


class PapersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: PapersUpdateData


class PapersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[PapersBatchUpdateItem]


class PapersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


async def _attach_uploader_info(db: AsyncSession, papers):
    if not papers:
        return []

    user_ids = {paper.user_id for paper in papers if getattr(paper, 'user_id', None)}
    if not user_ids:
        return [dict({k: v for k, v in paper.__dict__.items() if not k.startswith('_')}, uploader_display_name=None, uploader_profile_picture_key=None) for paper in papers]

    result = await db.execute(select(User_profiles).where(User_profiles.user_id.in_(user_ids)))
    profiles = result.scalars().all()
    profile_map = {profile.user_id: profile for profile in profiles}

    serialized = []
    for paper in papers:
        paper_data = {k: v for k, v in paper.__dict__.items() if not k.startswith('_')}
        profile = profile_map.get(paper.user_id)
        paper_data['uploader_display_name'] = profile.display_name if profile else None
        paper_data['uploader_profile_picture_key'] = profile.profile_picture_key if profile else None
        serialized.append(paper_data)
    return serialized


def _load_mock_papers(query_dict=None, sort=None, skip=0, limit=20):
    if not MOCK_PAPERS_PATH.exists():
        raise FileNotFoundError("Mock papers file not found")

    raw_items = json.loads(MOCK_PAPERS_PATH.read_text(encoding="utf-8"))
    items = []
    for entry in raw_items:
        entry = {**entry}
        if query_dict and any(entry.get(key) != value for key, value in query_dict.items()):
            continue
        items.append(entry)

    if sort:
        reverse = sort.startswith("-")
        field_name = sort[1:] if reverse else sort
        items.sort(key=lambda item: item.get(field_name) or 0, reverse=reverse)

    total = len(items)
    return {
        "items": items[skip : skip + limit],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ---------- Routes ----------
@router.post("/{paper_id}/index")
async def index_paper_passages(
    paper_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper or paper.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Paper not found")
    return await PassageIndexService(db).index_paper(paper)


@router.get("/{paper_id}/index-status")
async def paper_index_status(
    paper_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper or paper.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Paper not found")
    from models.papers import PaperPassage
    row = (await db.execute(select(func.count(PaperPassage.id), func.sum(case((PaperPassage.embedding_status == "ready", 1), else_=0))).where(PaperPassage.paper_id == paper_id))).one()
    return {"paper_id": paper_id, "passages": row[0] or 0, "embedded": row[1] or 0}


@router.get("/{paper_id}/questions")
async def paper_questions(paper_id: int, current_user: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    paper = await db.get(Papers, paper_id)
    if not paper or paper.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Paper not found")
    from models.papers import PaperQuestion, QuestionClassification, QuestionTopic
    questions = (await db.execute(select(PaperQuestion).where(PaperQuestion.paper_id == paper_id).order_by(PaperQuestion.page_start, PaperQuestion.question_number))).scalars().all()
    items = []
    for question in questions:
        topics = (await db.execute(select(QuestionTopic).where(QuestionTopic.question_id == question.id))).scalars().all()
        classification = (await db.execute(select(QuestionClassification).where(QuestionClassification.question_id == question.id).order_by(QuestionClassification.id.desc()).limit(1))).scalar_one_or_none()
        items.append({"id": question.id, "number": question.question_number, "text": question.text, "page_start": question.page_start, "status": question.classification_status, "topics": [{"topic": topic.topic, "subtopic": topic.subtopic, "confidence": topic.confidence} for topic in topics], "types": classification.question_types.split(",") if classification and classification.question_types else [], "difficulty": classification.difficulty if classification else "Unknown", "difficulty_confidence": classification.difficulty_confidence if classification else None})
    return {"items": items}


@router.get("", response_model=PapersListResponse)
async def query_paperss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query paperss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying paperss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = PapersService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
            user_id=str(current_user.id),
        )
        result['items'] = await _attach_uploader_info(db, result['items'])
        logger.debug(f"Found {result['total']} paperss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying paperss: {str(e)}", exc_info=True)
        # Do not mask database failures with a mock-file error. The chained
        # exception and traceback keep the operational cause available in logs.
        raise HTTPException(status_code=500, detail="Failed to query papers") from e


@router.get("/all", response_model=PapersListResponse)
async def query_paperss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query paperss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying paperss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = PapersService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        result['items'] = await _attach_uploader_info(db, result['items'])
        logger.debug(f"Found {result['total']} paperss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying paperss: {str(e)}", exc_info=True)
        # Do not mask database failures with a mock-file error. The chained
        # exception and traceback keep the operational cause available in logs.
        raise HTTPException(status_code=500, detail="Failed to query papers") from e


@router.get("/{id}", response_model=PapersResponse)
async def get_papers(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single papers by ID (user can only see their own records)"""
    logger.debug(f"Fetching papers with id: {id}, fields={fields}")
    
    service = PapersService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Papers with id {id} not found")
            raise HTTPException(status_code=404, detail="Papers not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching papers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=PapersResponse, status_code=201)
async def create_papers(
    data: PapersData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new papers"""
    await require_upload_permission(current_user)
    logger.debug(f"Creating new papers with data: {data}")
    
    service = PapersService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create papers")
        
        logger.info(f"Papers created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating papers: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating papers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[PapersResponse], status_code=201)
async def create_paperss_batch(
    request: PapersBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple paperss in a single request"""
    await require_upload_permission(current_user)
    logger.debug(f"Batch creating {len(request.items)} paperss")
    
    service = PapersService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} paperss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[PapersResponse])
async def update_paperss_batch(
    request: PapersBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple paperss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} paperss")
    
    service = PapersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} paperss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=PapersResponse)
async def update_papers(
    id: int,
    data: PapersUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing papers (requires ownership)"""
    logger.debug(f"Updating papers {id} with data: {data}")
    existing = await db.get(Papers, id)
    if not existing:
        raise HTTPException(status_code=404, detail="Papers not found")
    await require_paper_management(db, current_user, existing)

    service = PapersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Papers with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Papers not found")
        
        logger.info(f"Papers {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating papers {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating papers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_paperss_batch(
    request: PapersBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple paperss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} paperss")
    
    service = PapersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} paperss successfully")
        return {"message": f"Successfully deleted {deleted_count} paperss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_papers(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single papers by ID (requires ownership)"""
    logger.debug(f"Deleting papers with id: {id}")
    existing = await db.get(Papers, id)
    if not existing:
        raise HTTPException(status_code=404, detail="Papers not found")
    await require_paper_management(db, current_user, existing)
    
    service = PapersService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Papers with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Papers not found")
        
        logger.info(f"Papers {id} deleted successfully")
        return {"message": "Papers deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting papers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
