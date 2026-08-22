import logging
from datetime import datetime, timezone

from dependencies.auth import get_admin_user, get_current_user, get_optional_current_user
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.books import Book
from models.papers import Papers
from models.user_profiles import User_profiles
from services.authorization import can_read_book
from schemas.auth import UserResponse
from schemas.storage import (
    BucketListResponse,
    BucketRequest,
    BucketResponse,
    DeleteResponse,
    FileUpDownRequest,
    FileUpDownResponse,
    FileUploadResponse,
    ObjectInfo,
    ObjectListResponse,
    ObjectRequest,
    OSSBaseModel,
    RenameRequest,
    RenameResponse,
)
from services.storage import StorageService
from services.pdf_text import extract_pdf_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


async def _require_read_access(
    bucket_name: str,
    object_key: str,
    current_user: UserResponse | None,
    db: AsyncSession,
) -> None:
    """Authorize stored resource files by their database ownership and visibility."""
    if bucket_name == "books":
        book = (await db.execute(
            select(Book).where(
                or_(Book.file_key == object_key, Book.cover_key == object_key),
            )
        )).scalar_one_or_none()
        if not book:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored book file not found")
        if not can_read_book(current_user, book):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book file not found")
        return

    if bucket_name == "papers":
        paper = (await db.execute(
            select(Papers).where(
                or_(Papers.file_key == object_key, Papers.solution_key == object_key),
            )
        )).scalar_one_or_none()
        if not paper or (current_user and current_user.role != "admin" and paper.is_hidden) or (current_user is None and paper.is_hidden):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper file not found")
        return

    if bucket_name == "profiles":
        profile = (await db.execute(select(User_profiles).where(User_profiles.profile_picture_key == object_key))).scalar_one_or_none()
        if not profile and (current_user is None or current_user.role != "admin"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile image not found")
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Storage object access is not permitted")


@router.post("/analyze-pdf")
async def analyze_pdf_upload(
    file: UploadFile = File(...),
    _current_user: UserResponse = Depends(get_current_user),
):
    """Return bounded readable text for client-side form suggestions; never stores the file."""
    if not (file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files can be analysed")
    file_bytes = await file.read(12 * 1024 * 1024 + 1)
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The PDF is empty")
    if len(file_bytes) > 12 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Use a PDF smaller than 12 MB for automatic suggestions")

    text = extract_pdf_text(file_bytes)
    return {"text": text, "has_readable_text": bool(text)}


@router.post("/create-bucket", response_model=BucketResponse)
async def create_bucket(request: BucketRequest, _current_user: UserResponse = Depends(get_admin_user)):
    """
    Create a new bucket
    """
    try:
        service = StorageService()
        return await service.create_bucket(request)
    except ValueError as e:
        logger.error(f"Invalid create bucket request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create bucket: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.get("/list-buckets", response_model=BucketListResponse)
async def list_buckets(_current_user: UserResponse = Depends(get_admin_user)):
    """
    List buckets of the user
    """
    try:
        service = StorageService()
        return await service.list_buckets()
    except ValueError as e:
        logger.error(f"Invalid list buckets request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list buckets: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.get("/list-objects", response_model=ObjectListResponse)
async def list_objects(request: OSSBaseModel = Depends(), _current_user: UserResponse = Depends(get_admin_user)):
    """
    List objects under the bucket
    """
    try:
        service = StorageService()
        return await service.list_objects(request)
    except ValueError as e:
        logger.error(f"Invalid list objects request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list objects: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.get("/get-object-info", response_model=ObjectInfo)
async def get_object_info(request: ObjectRequest = Depends(), _current_user: UserResponse = Depends(get_admin_user)):
    """
    Get object metadata from the bucket
    """
    try:
        service = StorageService()
        return await service.get_object_info(request)
    except ValueError as e:
        logger.error(f"Invalid get object metadata request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get object metadata: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.post("/rename-object", response_model=RenameResponse)
async def rename_object(request: RenameRequest, _current_user: UserResponse = Depends(get_admin_user)):
    """
    Rename object inside the bucket
    """
    try:
        service = StorageService()
        return await service.rename_object(request)
    except ValueError as e:
        logger.error(f"Invalid rename object: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to rename object: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.delete("/delete-object", response_model=DeleteResponse)
async def delete_object(request: ObjectRequest, _current_user: UserResponse = Depends(get_admin_user)):
    """
    Delete object inside the bucket
    """
    try:
        service = StorageService()
        return await service.delete_object(request)
    except ValueError as e:
        logger.error(f"Invalid delete object: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete object: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.post("/upload-url", response_model=FileUpDownResponse)
async def upload_file(request: FileUpDownRequest, _current_user: UserResponse = Depends(get_current_user)):
    """
    Get a presigned URL for uploading a file to StorageService.

    Steps:
    1. Client calls this endpoint with file details
    2. Server validates and calls OSS service
    3. Returns presigned URL and access_url from OSS service
    4. Client uploads file directly to ObjectStorage using the presigned URL
    5. File is accessible at the returned access_url
    """
    try:
        if request.bucket_name in {"books", "book-covers", "papers"} and _current_user.role not in {"admin", "cp"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators and CPs can upload academic resources")
        service = StorageService()
        return await service.create_upload_url(request)
    except ValueError as e:
        logger.error(f"Invalid upload request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate upload URL: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file_direct(
    bucket_name: str = Form(...),
    object_key: str = Form(...),
    file: UploadFile = File(...),
    _current_user: UserResponse = Depends(get_current_user),
):
    """
    Upload a file to the configured storage backend through the backend.
    """
    try:
        if bucket_name in {"books", "book-covers", "papers"} and _current_user.role not in {"admin", "cp"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators and CPs can upload academic resources")
        request = FileUpDownRequest(bucket_name=bucket_name, object_key=object_key)
        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Uploaded file is empty")

        service = StorageService()
        stored_object_key = await service.upload_file(
            request.bucket_name,
            request.object_key,
            file_bytes,
            file.content_type,
        )
        return FileUploadResponse(object_key=stored_object_key)
    except ValueError as e:
        logger.error(f"Invalid upload request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.get("/download")
async def download_file_direct(
    bucket_name: str,
    object_key: str,
    current_user: UserResponse | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download a file from the configured storage backend through the backend.
    """
    try:
        await _require_read_access(bucket_name, object_key, current_user, db)
        request = FileUpDownRequest(bucket_name=bucket_name, object_key=object_key)
        service = StorageService()
        file_bytes = await service.download_file(request.bucket_name, request.object_key)
        metadata = await service.get_file_metadata(request.bucket_name, request.object_key)
        return Response(
            content=file_bytes,
            media_type=metadata.get("mime_type") or "application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=\"{metadata.get('file_name') or request.object_key}\"",
            },
        )
    except ValueError as e:
        logger.error(f"Invalid download request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.post("/google-drive-test")
async def google_drive_test(_current_user: UserResponse = Depends(get_admin_user)):
    """
    Test Google Drive authentication, upload, and delete operations.
    """
    try:
        service = StorageService()
        test_bucket = "google-drive-debug"
        test_name = f"test-upload-{int(datetime.now(timezone.utc).timestamp())}.txt"
        file_bytes = b"Google Drive integration test"

        object_key = await service.upload_file(test_bucket, test_name, file_bytes, "text/plain")
        metadata = await service.get_file_metadata(test_bucket, object_key)
        await service.delete_object(ObjectRequest(bucket_name=test_bucket, object_key=object_key))

        return {
            "success": True,
            "drive_file_id": metadata.get("drive_file_id"),
            "file_name": metadata.get("file_name"),
            "mime_type": metadata.get("mime_type"),
        }
    except ValueError as e:
        logger.error(f"Google Drive test failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Google Drive test failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")


@router.post("/download-url", response_model=FileUpDownResponse)
async def download_file(
    request: FileUpDownRequest,
    _current_user: UserResponse | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a presigned URL for downloading a file to StorageService.
    """
    try:
        await _require_read_access(request.bucket_name, request.object_key, _current_user, db)
        service = StorageService()
        return await service.create_download_url(request)
    except ValueError as e:
        logger.error(f"Invalid download request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate download URL: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")
