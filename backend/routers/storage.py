import logging
from dataclasses import dataclass
from urllib.parse import urlparse
from datetime import datetime, timezone

from dependencies.auth import get_admin_user, get_current_user, get_optional_current_user
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.books import Book
from models.papers import Papers
from models.solutions import Solutions
from models.user_profiles import User_profiles
from services.authorization import can_read_book, has_permission
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
from services.storage import StorageService, storage_key_candidates
from services.pdf_text import extract_pdf_text
from services.site_access import require_resource_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@dataclass(frozen=True)
class AuthorizedStorageObject:
    bucket_name: str
    logical_object_key: str
    provider_file_id: str | None
    storage_provider: str | None
    entity_type: str
    entity_id: int | str
    record: object | None = None


async def _cache_provider_metadata(resolved: AuthorizedStorageObject, metadata: dict, db: AsyncSession) -> None:
    if not resolved.record or not metadata.get("drive_file_id"):
        return
    record = resolved.record
    if resolved.entity_type == "book":
        is_cover = resolved.logical_object_key == getattr(record, "cover_key", None)
        setattr(record, "cover_drive_file_id" if is_cover else "file_drive_file_id", metadata["drive_file_id"])
        setattr(record, "cover_storage_provider" if is_cover else "file_storage_provider", metadata.get("storage_provider"))
    elif resolved.entity_type == "paper":
            is_solution = resolved.logical_object_key == getattr(record, "solution_key", None)
            is_cover = resolved.logical_object_key == getattr(record, "cover_key", None)
            prefix = "solution" if is_solution else "cover" if is_cover else "file"
            setattr(record, f"{prefix}_drive_file_id", metadata["drive_file_id"])
            setattr(record, f"{prefix}_storage_provider", metadata.get("storage_provider"))
    elif resolved.entity_type == "solution":
        record.drive_file_id = metadata["drive_file_id"]
        record.storage_provider = metadata.get("storage_provider")
    await db.commit()


async def _require_read_access(
    bucket_name: str,
    object_key: str,
    current_user: UserResponse | None,
    db: AsyncSession,
) -> "AuthorizedStorageObject":
    """Authorize a database-owned object and return its canonical key."""
    return await _resolve_authorized_object(bucket_name, object_key, current_user, db)


def _is_external_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


async def _resolve_authorized_object(bucket_name: str, requested_key: str, current_user, db: AsyncSession) -> AuthorizedStorageObject:
    """Resolve legacy key shapes through a resource record before touching storage.

    The request never becomes a general object-store read: every accepted variant
    must identify a Paper, Book, or profile row and is then replaced with its
    database-owned canonical key.
    """
    if _is_external_url(requested_key):
        raise HTTPException(status_code=400, detail="External URLs are not storage object keys")
    candidates = storage_key_candidates(bucket_name, requested_key)
    if bucket_name in {"books", "book-covers"}:
        book = (await db.execute(select(Book).where(or_(*[
            Book.file_key.in_(candidates), Book.cover_key.in_(candidates)
        ])))).scalar_one_or_none()
        if not book or not can_read_book(current_user, book):
            raise HTTPException(status_code=404, detail="Book file not found")
        key = next(key for key in (book.file_key, book.cover_key) if key in candidates)
        is_cover = key == book.cover_key
        return AuthorizedStorageObject(
            bucket_name, key,
            getattr(book, "cover_drive_file_id" if is_cover else "file_drive_file_id"),
            getattr(book, "cover_storage_provider" if is_cover else "file_storage_provider"),
            "book", book.id, book,
        )
    if bucket_name in {"papers", "solutions"}:
        paper = (await db.execute(select(Papers).where(or_(
            Papers.file_key.in_(candidates), Papers.cover_key.in_(candidates), Papers.solution_key.in_(candidates)
        )))).scalar_one_or_none()
        solution = (await db.execute(select(Solutions).where(Solutions.file_key.in_(candidates)))).scalar_one_or_none()
        if paper and (paper.is_hidden and (not current_user or not has_permission(current_user, "papers.edit"))):
            raise HTTPException(status_code=404, detail="Paper file not found")
        if paper:
            key = next(key for key in (paper.file_key, paper.solution_key) if key in candidates)
            is_solution = key == paper.solution_key
            return AuthorizedStorageObject(
                bucket_name, key,
                getattr(paper, "solution_drive_file_id" if is_solution else "file_drive_file_id"),
                getattr(paper, "solution_storage_provider" if is_solution else "file_storage_provider"),
                "paper", paper.id, paper,
            )
        if solution:
            paper_visibility = await db.execute(select(Papers.is_hidden).where(Papers.id == solution.paper_id))
            is_hidden = paper_visibility.scalar_one_or_none()
            if is_hidden and (not current_user or not has_permission(current_user, "papers.edit")):
                raise HTTPException(status_code=404, detail="Solution file not found")
            return AuthorizedStorageObject(bucket_name, solution.file_key, solution.drive_file_id, solution.storage_provider, "solution", solution.id, solution)
        logger.warning(
            "Storage object authorization failed: entity_type=%s entity_id=%s db_key=%r bucket=%s candidates=%s",
            "paper_or_solution", "unknown", requested_key, bucket_name, candidates,
        )
        raise HTTPException(status_code=404, detail="Paper file not found")
    if bucket_name == "profiles":
        profile = (await db.execute(select(User_profiles).where(User_profiles.profile_picture_key.in_(candidates)))).scalar_one_or_none()
        if not profile and (not current_user or not has_permission(current_user, "users.manage")):
            raise HTTPException(status_code=404, detail="Profile image not found")
        return AuthorizedStorageObject(
            bucket_name, profile.profile_picture_key if profile else requested_key,
            None, None, "profile", profile.id if profile else "unknown",
        )
    raise HTTPException(status_code=403, detail="Storage object access is not permitted")


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
async def upload_file(request: FileUpDownRequest, _current_user: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
        resource_type = {"books": "book", "book-covers": "book", "papers": "paper"}.get(request.bucket_name)
        if resource_type:
            await require_resource_upload(db, _current_user, resource_type)
        service = StorageService()
        return await service.create_upload_url(request)
    except HTTPException:
        raise
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
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a file to the configured storage backend through the backend.
    """
    try:
        resource_type = {"books": "book", "book-covers": "book", "papers": "paper"}.get(bucket_name)
        if resource_type:
            await require_resource_upload(db, _current_user, resource_type)
        request = FileUpDownRequest(bucket_name=bucket_name, object_key=object_key)
        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Uploaded file is empty")

        service = StorageService()
        upload_result = await service.upload_file_with_metadata(
            request.bucket_name,
            request.object_key,
            file_bytes,
            file.content_type,
        )
        return FileUploadResponse(
            object_key=upload_result.object_key,
            provider_file_id=upload_result.provider_file_id,
            storage_provider=upload_result.storage_provider,
        )
    except HTTPException:
        raise
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
        resolved = await _resolve_authorized_object(bucket_name, object_key, current_user, db)
        request = FileUpDownRequest(bucket_name=bucket_name, object_key=resolved.logical_object_key)
        service = StorageService()
        last_error = None
        file_bytes = None
        if resolved.provider_file_id:
            try:
                file_bytes = await service.download_file_by_id(request.bucket_name, request.object_key, resolved.provider_file_id)
                metadata = await service.get_file_metadata_by_id(request.bucket_name, request.object_key, resolved.provider_file_id)
                logger.info(
                    "Storage resolved bucket=%s logical_object_key=%s provider=%s provider_file_id=%s parent_folder_id=%s resolution_method=file_id entity_type=%s entity_id=%s",
                    request.bucket_name, resolved.logical_object_key, resolved.storage_provider,
                    resolved.provider_file_id, metadata.get("parent_folder_id"), resolved.entity_type, resolved.entity_id,
                )
            except ValueError as exc:
                last_error = exc
        else:
            for provider_key in storage_key_candidates(request.bucket_name, request.object_key):
                try:
                    file_bytes = await service.download_file(request.bucket_name, provider_key)
                    metadata = await service.get_file_metadata(request.bucket_name, provider_key)
                    await _cache_provider_metadata(resolved, metadata, db)
                    logger.info(
                        "Storage resolved bucket=%s logical_object_key=%s canonical_object_key=%s provider=%s provider_file_id=%s parent_folder_id=%s resolution_method=%s entity_type=%s entity_id=%s",
                        request.bucket_name, resolved.logical_object_key, provider_key,
                        metadata.get("storage_provider"), metadata.get("drive_file_id"), metadata.get("parent_folder_id"),
                        "exact_name" if provider_key == request.object_key else "legacy_fallback",
                        resolved.entity_type, resolved.entity_id,
                    )
                    break
                except ValueError as exc:
                    last_error = exc
        if file_bytes is None:
            logger.warning(
                "Storage object resolution failed: entity_type=%s entity_id=%s db_key=%r bucket=%s candidates=%s error=%s",
                resolved.entity_type, resolved.entity_id, request.object_key, request.bucket_name,
                storage_key_candidates(request.bucket_name, request.object_key), last_error,
            )
            raise HTTPException(status_code=404, detail="Stored object not found") from last_error
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
        resolved = await _require_read_access(request.bucket_name, request.object_key, _current_user, db)
        service = StorageService()
        if resolved.provider_file_id:
            metadata = await service.get_file_metadata_by_id(request.bucket_name, resolved.logical_object_key, resolved.provider_file_id)
            logger.info(
                "Storage resolved bucket=%s logical_object_key=%s provider=%s provider_file_id=%s parent_folder_id=%s resolution_method=file_id entity_type=%s entity_id=%s",
                request.bucket_name, resolved.logical_object_key, resolved.storage_provider,
                resolved.provider_file_id, metadata.get("parent_folder_id"), resolved.entity_type, resolved.entity_id,
            )
            return await service.create_download_url(FileUpDownRequest(bucket_name=request.bucket_name, object_key=resolved.logical_object_key))
        return await service.create_download_url(FileUpDownRequest(bucket_name=request.bucket_name, object_key=resolved.logical_object_key))
    except ValueError as e:
        logger.error(f"Invalid download request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate download URL: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e}")
