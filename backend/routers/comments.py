import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.comments import CommentsService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/comments", tags=["comments"])


# ---------- Pydantic Schemas ----------
class CommentsData(BaseModel):
    """Entity data schema (for create/update)"""
    paper_id: Optional[int] = None
    book_id: Optional[int] = None
    content: str
    parent_id: int = None
    upvotes: int = None
    created_at: Optional[datetime] = None


class CommentsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    paper_id: Optional[int] = None
    book_id: Optional[int] = None
    content: Optional[str] = None
    parent_id: Optional[int] = None
    upvotes: Optional[int] = None
    created_at: Optional[datetime] = None


class CommentsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    paper_id: Optional[int] = None
    book_id: Optional[int] = None
    content: str
    parent_id: Optional[int] = None
    upvotes: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CommentsListResponse(BaseModel):
    """List response schema"""
    items: List[CommentsResponse]
    total: int
    skip: int
    limit: int


class CommentsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[CommentsData]


class CommentsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: CommentsUpdateData


class CommentsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[CommentsBatchUpdateItem]


class CommentsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=CommentsListResponse)
async def query_commentss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query commentss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying commentss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = CommentsService(db)
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
        logger.debug(f"Found {result['total']} commentss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying commentss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=CommentsListResponse)
async def query_commentss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query commentss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying commentss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = CommentsService(db)
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
        logger.debug(f"Found {result['total']} commentss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying commentss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=CommentsResponse)
async def get_comments(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single comments by ID (user can only see their own records)"""
    logger.debug(f"Fetching comments with id: {id}, fields={fields}")
    
    service = CommentsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Comments with id {id} not found")
            raise HTTPException(status_code=404, detail="Comments not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching comments {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=CommentsResponse, status_code=201)
async def create_comments(
    data: CommentsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new comments"""
    logger.debug(f"Creating new comments with data: {data}")
    
    service = CommentsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create comments")
        
        logger.info(f"Comments created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating comments: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating comments: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[CommentsResponse], status_code=201)
async def create_commentss_batch(
    request: CommentsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple commentss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} commentss")
    
    service = CommentsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} commentss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[CommentsResponse])
async def update_commentss_batch(
    request: CommentsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple commentss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} commentss")
    
    service = CommentsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} commentss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=CommentsResponse)
async def update_comments(
    id: int,
    data: CommentsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing comments (requires ownership)"""
    logger.debug(f"Updating comments {id} with data: {data}")

    service = CommentsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Comments with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Comments not found")
        
        logger.info(f"Comments {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating comments {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating comments {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_commentss_batch(
    request: CommentsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple commentss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} commentss")
    
    service = CommentsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} commentss successfully")
        return {"message": f"Successfully deleted {deleted_count} commentss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_comments(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single comments by ID (requires ownership)"""
    logger.debug(f"Deleting comments with id: {id}")
    
    service = CommentsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Comments with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Comments not found")
        
        logger.info(f"Comments {id} deleted successfully")
        return {"message": "Comments deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting comments {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")