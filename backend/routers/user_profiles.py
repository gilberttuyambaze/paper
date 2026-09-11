import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.user_profiles import User_profilesService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services.authorization import is_admin_or_super_admin

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/user_profiles", tags=["user_profiles"])


# ---------- Pydantic Schemas ----------
class User_profilesData(BaseModel):
    """Entity data schema (for create/update)"""
    display_name: str
    role: str
    trust_score: Optional[int] = None
    upload_count: Optional[int] = None
    download_count: Optional[int] = None
    institution_type: Optional[str] = None
    university_name: Optional[str] = None
    ur_student_code: Optional[str] = None
    ur_verification_status: Optional[str] = None
    profile_picture_key: Optional[str] = None
    phone_number: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    institution_id: Optional[str] = None
    campus_id: Optional[str] = None
    college_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_department_id: Optional[str] = None
    programme_id: Optional[str] = None
    programme_submission_id: Optional[int] = None
    programme_name_other: Optional[str] = None
    programme_name_normalized: Optional[str] = None
    academic_programme_status: Optional[str] = None
    year_of_study: Optional[str] = None
    bio: Optional[str] = None
    requested_role: Optional[str] = None
    requested_role_status: Optional[str] = None
    account_status: Optional[str] = None
    suspension_reason: Optional[str] = None
    suspended_until: Optional[datetime] = None
    created_at: Optional[datetime] = None


class User_profilesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    display_name: Optional[str] = None
    role: Optional[str] = None
    trust_score: Optional[int] = None
    upload_count: Optional[int] = None
    download_count: Optional[int] = None
    institution_type: Optional[str] = None
    university_name: Optional[str] = None
    ur_student_code: Optional[str] = None
    ur_verification_status: Optional[str] = None
    profile_picture_key: Optional[str] = None
    phone_number: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    institution_id: Optional[str] = None
    campus_id: Optional[str] = None
    college_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_department_id: Optional[str] = None
    programme_id: Optional[str] = None
    programme_submission_id: Optional[int] = None
    programme_name_other: Optional[str] = None
    programme_name_normalized: Optional[str] = None
    academic_programme_status: Optional[str] = None
    year_of_study: Optional[str] = None
    bio: Optional[str] = None
    requested_role: Optional[str] = None
    requested_role_status: Optional[str] = None
    account_status: Optional[str] = None
    suspension_reason: Optional[str] = None
    suspended_until: Optional[datetime] = None
    created_at: Optional[datetime] = None


class User_profilesResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    display_name: str
    role: str
    trust_score: Optional[int] = None
    upload_count: Optional[int] = None
    download_count: Optional[int] = None
    institution_type: Optional[str] = None
    university_name: Optional[str] = None
    ur_student_code: Optional[str] = None
    ur_verification_status: Optional[str] = None
    profile_picture_key: Optional[str] = None
    phone_number: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    institution_id: Optional[str] = None
    campus_id: Optional[str] = None
    college_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_department_id: Optional[str] = None
    programme_id: Optional[str] = None
    programme_submission_id: Optional[int] = None
    programme_name_other: Optional[str] = None
    programme_name_normalized: Optional[str] = None
    academic_programme_status: Optional[str] = None
    year_of_study: Optional[str] = None
    bio: Optional[str] = None
    requested_role: Optional[str] = None
    requested_role_status: Optional[str] = None
    account_status: Optional[str] = None
    suspension_reason: Optional[str] = None
    suspended_until: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class User_profilesListResponse(BaseModel):
    """List response schema"""
    items: List[User_profilesResponse]
    total: int
    skip: int
    limit: int


class User_profilesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[User_profilesData]


class User_profilesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: User_profilesUpdateData


class User_profilesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[User_profilesBatchUpdateItem]


class User_profilesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=User_profilesListResponse)
async def query_user_profiless(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query user_profiless with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying user_profiless: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = User_profilesService(db)
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
        logger.debug(f"Found {result['total']} user_profiless")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying user_profiless: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=User_profilesListResponse)
async def query_user_profiless_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query user_profiless with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying user_profiless: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = User_profilesService(db)
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
        logger.debug(f"Found {result['total']} user_profiless")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying user_profiless: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=User_profilesResponse)
async def get_user_profiles(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single user_profiles by ID (user can only see their own records)"""
    logger.debug(f"Fetching user_profiles with id: {id}, fields={fields}")
    
    service = User_profilesService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"User_profiles with id {id} not found")
            raise HTTPException(status_code=404, detail="User_profiles not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=User_profilesResponse, status_code=201)
async def create_user_profiles(
    data: User_profilesData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user_profiles"""
    logger.debug(f"Creating new user_profiles with data: {data}")
    
    service = User_profilesService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create user_profiles")
        
        logger.info(f"User_profiles created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating user_profiles: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating user_profiles: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[User_profilesResponse], status_code=201)
async def create_user_profiless_batch(
    request: User_profilesBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple user_profiless in a single request"""
    logger.debug(f"Batch creating {len(request.items)} user_profiless")
    
    service = User_profilesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} user_profiless successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


PRIVILEGED_PROFILE_FIELDS = frozenset({
    "role", "trust_score", "account_status", "ur_verification_status",
    "upload_count", "download_count", "suspension_reason", "suspended_until",
    "requested_role_status"
})


def _validate_self_profile_update(current_user: UserResponse, update_dict: dict) -> None:
    if not is_admin_or_super_admin(current_user):
        attempted_privileged = set(update_dict.keys()) & PRIVILEGED_PROFILE_FIELDS
        if attempted_privileged:
            raise HTTPException(
                status_code=403,
                detail=f"You do not have permission to modify privileged fields: {', '.join(sorted(attempted_privileged))}",
            )


@router.put("/batch", response_model=List[User_profilesResponse])
async def update_user_profiless_batch(
    request: User_profilesBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple user_profiless in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} user_profiless")
    
    service = User_profilesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            _validate_self_profile_update(current_user, update_dict)
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} user_profiless successfully")
        return results
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=User_profilesResponse)
async def update_user_profiles(
    id: int,
    data: User_profilesUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing user_profiles (requires ownership)"""
    logger.debug(f"Updating user_profiles {id} with data: {data}")

    service = User_profilesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        _validate_self_profile_update(current_user, update_dict)
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"User_profiles with id {id} not found for update")
            raise HTTPException(status_code=404, detail="User_profiles not found")
        
        logger.info(f"User_profiles {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating user_profiles {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating user_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_user_profiless_batch(
    request: User_profilesBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple user_profiless by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} user_profiless")
    
    service = User_profilesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} user_profiless successfully")
        return {"message": f"Successfully deleted {deleted_count} user_profiless", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_user_profiles(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single user_profiles by ID (requires ownership)"""
    logger.debug(f"Deleting user_profiles with id: {id}")
    
    service = User_profilesService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"User_profiles with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="User_profiles not found")
        
        logger.info(f"User_profiles {id} deleted successfully")
        return {"message": "User_profiles deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")