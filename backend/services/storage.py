import asyncio
import base64
import importlib
import io
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import quote

import httpx

from core.config import settings
from schemas.storage import (
    BucketInfo,
    BucketListResponse,
    BucketRequest,
    BucketResponse,
    DeleteResponse,
    FileUpDownRequest,
    FileUpDownResponse,
    ObjectInfo,
    ObjectListResponse,
    ObjectRequest,
    OSSBaseModel,
    RenameRequest,
    RenameResponse,
)

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "application/epub+zip",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "text/plain",
}
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".epub", ".png", ".jpg", ".jpeg", ".txt"}


def _normalize_content_type(content_type: Optional[str]) -> Optional[str]:
    if not content_type:
        return None
    return content_type.split(";")[0].strip().lower()


def _escape_drive_query_value(value: str) -> str:
    return value.replace("'", "\\'")


def _validate_upload_type(object_key: str, content_type: Optional[str]) -> None:
    normalized_content_type = _normalize_content_type(content_type)
    ext = Path(object_key).suffix.lower()
    if normalized_content_type:
        if normalized_content_type not in ALLOWED_UPLOAD_MIME_TYPES and ext not in ALLOWED_UPLOAD_EXTENSIONS:
            raise ValueError(
                f"Unsupported upload content type: {normalized_content_type}. "
                f"Allowed MIME types: {', '.join(sorted(ALLOWED_UPLOAD_MIME_TYPES))}."
            )
    elif ext and ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(
            f"Unsupported upload extension: {ext}. "
            f"Allowed extensions: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}."
        )


class StorageServiceBase:
    async def create_bucket(self, request: BucketRequest) -> BucketResponse:
        raise NotImplementedError()

    async def list_buckets(self) -> BucketListResponse:
        raise NotImplementedError()

    async def list_objects(self, request: OSSBaseModel) -> ObjectListResponse:
        raise NotImplementedError()

    async def get_object_info(self, request: ObjectRequest) -> ObjectInfo:
        raise NotImplementedError()

    async def rename_object(self, request: RenameRequest) -> RenameResponse:
        raise NotImplementedError()

    async def delete_object(self, request: ObjectRequest) -> DeleteResponse:
        raise NotImplementedError()

    async def upload_file(
        self,
        bucket_name: str,
        object_key: str,
        file_bytes: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        raise NotImplementedError()

    async def download_file(self, bucket_name: str, object_key: str) -> bytes:
        raise NotImplementedError()

    async def get_file_url(self, bucket_name: str, object_key: str) -> str:
        raise NotImplementedError()

    async def get_file_metadata(self, bucket_name: str, object_key: str) -> dict[str, Any]:
        return {}

    async def create_upload_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        raise NotImplementedError()

    async def create_download_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        raise NotImplementedError()

    def _expires_at(self, hours: int = 0, minutes: int = 0) -> str:
        return (datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)).isoformat()


class SupabaseStorageService(StorageServiceBase):
    """Supabase Storage-backed file service."""

    def __init__(self):
        self.project_url = (
            getattr(settings, "supabase_url", None) or getattr(settings, "oss_service_url", None) or ""
        ).rstrip("/")
        self.service_key = (
            getattr(settings, "supabase_service_role_key", None)
            or getattr(settings, "supabase_service_key", None)
            or getattr(settings, "oss_api_key", None)
            or ""
        ).strip()
        self.default_bucket = (getattr(settings, "supabase_bucket", None) or "").strip()

        if not self.project_url or not self.service_key:
            raise ValueError(
                "Supabase storage is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY "
                "(or OSS_SERVICE_URL and OSS_API_KEY)."
            )
        if self.service_key.startswith("sb_publishable_"):
            raise ValueError(
                "SUPABASE_SERVICE_ROLE_KEY is set to a publishable key. "
                "Use the Supabase service_role key for backend storage operations."
            )

        self.api_base_url = f"{self.project_url}/storage/v1"
        self.headers = {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
            "Accept": "application/json",
        }

    async def create_bucket(self, request: BucketRequest) -> BucketResponse:
        payload = {
            "id": request.bucket_name,
            "name": request.bucket_name,
            "public": request.visibility == "public",
        }
        try:
            result = await self._request("POST", "/bucket", json=payload)
            bucket_name = result.get("id") or result.get("name") or request.bucket_name
            return BucketResponse(
                bucket_name=bucket_name,
                visibility="public" if result.get("public") else "private",
                created_at=result.get("created_at", ""),
            )
        except ValueError as exc:
            if self._is_already_exists_error(exc):
                return BucketResponse(
                    bucket_name=request.bucket_name,
                    visibility=request.visibility,
                    created_at="",
                )
            logger.error("Failed to create bucket: %s", exc)
            raise

    async def list_buckets(self) -> BucketListResponse:
        result = await self._request("GET", "/bucket")
        items = result if isinstance(result, list) else result.get("buckets", []) if isinstance(result, dict) else []
        return BucketListResponse(
            buckets=[
                BucketInfo(
                    bucket_name=item.get("id") or item.get("name") or "",
                    visibility="public" if item.get("public") else "private",
                )
                for item in items
            ]
        )

    async def list_objects(self, request: OSSBaseModel) -> ObjectListResponse:
        await self._ensure_bucket(request.bucket_name)
        result = await self._request(
            "POST",
            f"/object/list/{self._quote_bucket(request.bucket_name)}",
            json={"limit": 1000, "offset": 0},
        )
        items = result if isinstance(result, list) else []
        objects = [
            ObjectInfo(
                bucket_name=request.bucket_name,
                object_key=item.get("name", ""),
                size=item.get("metadata", {}).get("size") or item.get("size") or 0,
                last_modified=item.get("updated_at") or item.get("last_accessed_at") or "",
                etag=item.get("id") or "",
            )
            for item in items
        ]
        return ObjectListResponse(objects=objects)

    async def get_object_info(self, request: ObjectRequest) -> ObjectInfo:
        await self._ensure_bucket(request.bucket_name)
        try:
            result = await self._request("GET", f"/object/info/{self._object_path(request.bucket_name, request.object_key)}")
        except ValueError:
            result = await self._find_object_via_listing(request.bucket_name, request.object_key)
            if result is None:
                raise

        return ObjectInfo(
            bucket_name=request.bucket_name,
            object_key=result.get("name") or request.object_key,
            size=result.get("metadata", {}).get("size") or result.get("size") or 0,
            last_modified=result.get("updated_at") or result.get("last_accessed_at") or "",
            etag=result.get("id") or "",
        )

    async def get_file_metadata(self, bucket_name: str, object_key: str) -> dict[str, Any]:
        try:
            info = await self.get_object_info(ObjectRequest(bucket_name=bucket_name, object_key=object_key))
        except Exception:
            return {}

        return {
            "storage_provider": "supabase",
            "file_name": Path(object_key).name,
            "file_size": info.size,
            "mime_type": None,
        }

    async def rename_object(self, request: RenameRequest) -> RenameResponse:
        await self._ensure_bucket(request.bucket_name)
        payload = {
            "bucketId": request.bucket_name,
            "sourceKey": request.source_key,
            "destinationBucket": request.bucket_name,
            "destinationKey": request.target_key,
        }
        await self._request("POST", "/object/move", json=payload)
        return RenameResponse(success=True)

    async def delete_object(self, request: ObjectRequest) -> DeleteResponse:
        await self._request("DELETE", f"/object/{self._object_path(request.bucket_name, request.object_key)}")
        return DeleteResponse(success=True)

    async def upload_file(
        self,
        bucket_name: str,
        object_key: str,
        file_bytes: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        target_bucket = self._storage_bucket(bucket_name)
        await self._ensure_bucket(target_bucket)
        upload_headers = {
            **self.headers,
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "false",
        }
        await self._request(
            "POST",
            f"/object/{self._object_path(target_bucket, object_key)}",
            content=file_bytes,
            headers=upload_headers,
        )
        return object_key

    async def download_file(self, bucket_name: str, object_key: str) -> bytes:
        response = await self.create_download_url(FileUpDownRequest(bucket_name=bucket_name, object_key=object_key))
        async with httpx.AsyncClient(timeout=120.0) as client:
            download_response = await client.get(response.download_url)
            download_response.raise_for_status()
            return download_response.content

    async def get_file_url(self, bucket_name: str, object_key: str) -> str:
        response = await self.create_download_url(FileUpDownRequest(bucket_name=bucket_name, object_key=object_key))
        return response.download_url

    async def create_upload_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        raise ValueError(
            "Signed upload URLs are not used with the Supabase storage backend. "
            "Use the authenticated /api/v1/storage/upload endpoint instead."
        )

    async def create_download_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        target_bucket = self._storage_bucket(request.bucket_name)
        await self._ensure_bucket(target_bucket)
        result = await self._request(
            "POST",
            f"/object/sign/{self._object_path(target_bucket, request.object_key)}",
            json={"expiresIn": 3600, "download": True},
        )

        relative_url = result.get("signedURL") or result.get("signedUrl") or result.get("signed_url")
        if not relative_url:
            raise ValueError("Supabase did not return a signed download URL.")

        return FileUpDownResponse(
            download_url=self._absolute_storage_url(relative_url),
            expires_at=self._expires_at(hours=1),
        )

    async def _ensure_bucket(self, bucket_name: str) -> None:
        try:
            await self.create_bucket(BucketRequest(bucket_name=bucket_name, visibility="private"))
        except ValueError as exc:
            if self._is_already_exists_error(exc):
                return
            raise

    async def _find_object_via_listing(self, bucket_name: str, object_key: str) -> Optional[dict[str, Any]]:
        prefix = object_key.rsplit("/", 1)[0] if "/" in object_key else ""
        result = await self._request(
            "POST",
            f"/object/list/{self._quote_bucket(bucket_name)}",
            json={"limit": 1000, "offset": 0, "prefix": prefix},
        )
        target_name = object_key.split("/")[-1]
        for item in result if isinstance(result, list) else []:
            if item.get("name") == target_name:
                return item
        return None

    async def _request(
        self,
        method: Literal["GET", "POST", "DELETE"],
        path: str,
        json: Optional[dict[str, Any]] = None,
        content: Optional[bytes] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Any:
        url = f"{self.api_base_url}{path}"
        request_headers = headers or self.headers

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    json=json,
                    content=content,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            if exc.response.status_code in {401, 403} and self.service_key.startswith("sb_publishable_"):
                detail = (
                    f"{detail} Supabase rejected the publishable key. "
                    "Use SUPABASE_SERVICE_ROLE_KEY for backend storage operations."
                ).strip()
            raise ValueError(
                f"Supabase storage HTTP error: {exc.response.status_code} - {detail or 'Unknown error'}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Supabase storage request failed: {exc}") from exc

        if not response.content:
            return {}
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    def _quote_bucket(self, bucket_name: str) -> str:
        return quote(bucket_name, safe="")

    def _object_path(self, bucket_name: str, object_key: str) -> str:
        return f"{self._quote_bucket(bucket_name)}/{quote(object_key, safe='/')}"

    def _storage_bucket(self, bucket_name: str) -> str:
        return self.default_bucket or bucket_name

    def _absolute_storage_url(self, relative_url: str) -> str:
        if relative_url.startswith("http://") or relative_url.startswith("https://"):
            return relative_url
        if not relative_url.startswith("/"):
            relative_url = f"/{relative_url}"
        return f"{self.api_base_url}{relative_url}"

    def _is_already_exists_error(self, exc: ValueError) -> bool:
        message = str(exc).lower()
        return "already exists" in message or "duplicate" in message or "bucketid already exists" in message


class GoogleDriveStorageService(StorageServiceBase):
    def __init__(self):
        if not settings.google_drive_enabled:
            raise ValueError("Google Drive storage is not enabled. Set GOOGLE_DRIVE_ENABLED=true to use it.")

        self.root_folder_id = (settings.google_drive_folder_id or "").strip()
        self.service_account_json_base64 = (settings.google_service_account_json_base64 or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()

        if not self.root_folder_id:
            raise ValueError("Google Drive folder ID is required. Set GOOGLE_DRIVE_FOLDER_ID.")
        if not self.service_account_json_base64:
            raise ValueError("Google Drive service account JSON is required. Set GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 or GOOGLE_SERVICE_ACCOUNT_FILE.")

        # If GOOGLE_SERVICE_ACCOUNT_FILE points to a real file, load its contents
        if os.path.isfile(self.service_account_json_base64):
            with open(self.service_account_json_base64, "r", encoding="utf-8") as f:
                self.service_account_json_base64 = f.read().strip()

        google_oauth2 = self._import_google_module("google.oauth2.service_account")
        googleapiclient_discovery = self._import_google_module("googleapiclient.discovery")
        googleapiclient_errors = self._import_google_module("googleapiclient.errors")
        googleapiclient_http = self._import_google_module("googleapiclient.http")

        self.service_account_module = google_oauth2
        self.build = googleapiclient_discovery.build
        self.HttpError = googleapiclient_errors.HttpError
        self.MediaIoBaseDownload = googleapiclient_http.MediaIoBaseDownload
        self.MediaIoBaseUpload = googleapiclient_http.MediaIoBaseUpload

        self.credentials = self._load_credentials()
        self._service = self.build("drive", "v3", credentials=self.credentials, cache_discovery=False)
        self._download_metadata: dict[tuple[str, str], dict[str, Any]] = {}

    def _import_google_module(self, module_name: str):
        try:
            return importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(
                f"Google Drive support requires the '{module_name}' package. "
                "Install google-auth and google-api-python-client or disable GOOGLE_DRIVE_ENABLED."
            ) from exc

    def _load_credentials(self):
        try:
            service_account_json = base64.b64decode(self.service_account_json_base64).decode("utf-8")
            credentials_info = json.loads(service_account_json)
        except Exception as exc:
            raise ValueError("Invalid GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 value.") from exc

        try:
            return self.service_account_module.Credentials.from_service_account_info(
                credentials_info,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
        except Exception as exc:
            raise ValueError("Invalid Google service account credentials.") from exc

    async def _execute(self, request):
        try:
            return await asyncio.to_thread(request.execute)
        except self.HttpError as exc:
            detail = exc.args[0] if exc.args else str(exc)
            raise ValueError(f"Google Drive API error: {detail}") from exc

    async def _find_folder(self, folder_name: str, parent_id: str) -> Optional[str]:
        query = (
            f"name = '{_escape_drive_query_value(folder_name)}' "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false "
            f"and '{parent_id}' in parents"
        )
        response = await self._execute(
            self._service.files().list(
                q=query,
                spaces="drive",
                fields="files(id,name)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
        )
        files = response.get("files", [])
        return files[0]["id"] if files else None

    async def _ensure_folder(self, folder_name: str, parent_id: str) -> str:
        existing = await self._find_folder(folder_name, parent_id)
        if existing:
            return existing

        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        response = await self._execute(
            self._service.files().create(body=metadata, fields="id", supportsAllDrives=True)
        )
        return response["id"]

    async def _find_file(self, bucket_name: str, object_key: str) -> Optional[dict[str, Any]]:
        bucket_folder_id = await self._find_folder(bucket_name, self.root_folder_id)
        if not bucket_folder_id:
            return None

        segments = [segment for segment in object_key.split("/") if segment]
        if not segments:
            return None

        parent_id = bucket_folder_id
        for segment in segments[:-1]:
            parent_id = await self._find_folder(segment, parent_id)
            if not parent_id:
                return None

        file_name = segments[-1]
        query = (
            f"name = '{_escape_drive_query_value(file_name)}' "
            "and mimeType != 'application/vnd.google-apps.folder' "
            "and trashed = false "
            f"and '{parent_id}' in parents"
        )
        response = await self._execute(
            self._service.files().list(
                q=query,
                spaces="drive",
                fields="files(id,name,mimeType,size,modifiedTime)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
        )
        files = response.get("files", [])
        return files[0] if files else None

    async def _ensure_bucket_folder(self, bucket_name: str) -> str:
        return await self._ensure_folder(bucket_name, self.root_folder_id)

    async def _ensure_path_folder(self, bucket_name: str, object_key: str) -> str:
        parent_id = await self._ensure_bucket_folder(bucket_name)
        segments = [segment for segment in object_key.split("/")[:-1] if segment]
        for segment in segments:
            parent_id = await self._ensure_folder(segment, parent_id)
        return parent_id

    def _build_proxy_download_url(self, bucket_name: str, object_key: str) -> str:
        base_url = settings.backend_url.rstrip("/")
        encoded_bucket = quote(bucket_name, safe="")
        encoded_object = quote(object_key, safe="")
        return f"{base_url}/api/v1/storage/download?bucket_name={encoded_bucket}&object_key={encoded_object}"

    async def create_bucket(self, request: BucketRequest) -> BucketResponse:
        folder_id = await self._ensure_folder(request.bucket_name, self.root_folder_id)
        return BucketResponse(
            bucket_name=request.bucket_name,
            visibility="private",
            created_at="",
        )

    async def list_buckets(self) -> BucketListResponse:
        query = (
            "mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false "
            f"and '{self.root_folder_id}' in parents"
        )
        response = await self._execute(
            self._service.files().list(
                q=query,
                spaces="drive",
                fields="files(id,name)",
                pageSize=1000,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
        )
        files = response.get("files", [])
        return BucketListResponse(
            buckets=[BucketInfo(bucket_name=file.get("name", "")) for file in files]
        )

    async def _list_files_recursive(self, parent_id: str, prefix: str = "") -> list[ObjectInfo]:
        query = f"trashed = false and '{parent_id}' in parents"
        response = await self._execute(
            self._service.files().list(
                q=query,
                spaces="drive",
                fields="files(id,name,mimeType,size,modifiedTime)",
                pageSize=1000,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
        )
        objects: list[ObjectInfo] = []
        for item in response.get("files", []):
            if item.get("mimeType") == "application/vnd.google-apps.folder":
                nested_prefix = f"{prefix}{item.get('name')}/"
                objects.extend(await self._list_files_recursive(item["id"], nested_prefix))
            else:
                objects.append(
                    ObjectInfo(
                        bucket_name="",
                        object_key=f"{prefix}{item.get('name')}",
                        size=int(item.get("size") or 0),
                        last_modified=item.get("modifiedTime") or "",
                        etag=item.get("id") or "",
                    )
                )
        return objects

    async def list_objects(self, request: OSSBaseModel) -> ObjectListResponse:
        bucket_folder_id = await self._find_folder(request.bucket_name, self.root_folder_id)
        if not bucket_folder_id:
            return ObjectListResponse(objects=[])

        objects = await self._list_files_recursive(bucket_folder_id)
        for obj in objects:
            obj.bucket_name = request.bucket_name
        return ObjectListResponse(objects=objects)

    async def get_object_info(self, request: ObjectRequest) -> ObjectInfo:
        file = await self._find_file(request.bucket_name, request.object_key)
        if not file:
            raise ValueError("Google Drive file not found")
        return ObjectInfo(
            bucket_name=request.bucket_name,
            object_key=request.object_key,
            size=int(file.get("size") or 0),
            last_modified=file.get("modifiedTime") or "",
            etag=file.get("id") or "",
        )

    async def get_file_metadata(self, bucket_name: str, object_key: str) -> dict[str, Any]:
        file = self._download_metadata.pop((bucket_name, object_key), None)
        if not file:
            file = await self._find_file(bucket_name, object_key)
        if not file:
            raise ValueError("Google Drive file not found")
        return {
            "storage_provider": "google_drive",
            "drive_file_id": file.get("id"),
            "file_name": file.get("name"),
            "file_size": int(file.get("size") or 0),
            "mime_type": file.get("mimeType"),
        }

    async def rename_object(self, request: RenameRequest) -> RenameResponse:
        source_file = await self._find_file(request.bucket_name, request.source_key)
        if not source_file:
            raise ValueError("Source file not found")

        target_folder_id = await self._ensure_path_folder(request.bucket_name, request.target_key)
        target_file = await self._find_file(request.bucket_name, request.target_key)
        if target_file and not request.overwrite_key:
            raise ValueError("Target object already exists")
        if target_file and request.overwrite_key:
            await self._execute(self._service.files().delete(fileId=target_file["id"], supportsAllDrives=True))

        update_body = {"name": Path(request.target_key).name}
        request_update = self._service.files().update(
            fileId=source_file["id"],
            addParents=target_folder_id,
            removeParents=source_file.get("parents", [])[0] if source_file.get("parents") else None,
            body=update_body,
            fields="id",
            supportsAllDrives=True,
        )
        await self._execute(request_update)
        return RenameResponse(success=True)

    async def delete_object(self, request: ObjectRequest) -> DeleteResponse:
        file = await self._find_file(request.bucket_name, request.object_key)
        if not file:
            raise ValueError("Google Drive file not found")
        await self._execute(self._service.files().delete(fileId=file["id"], supportsAllDrives=True))
        return DeleteResponse(success=True)

    async def upload_file(
        self,
        bucket_name: str,
        object_key: str,
        file_bytes: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        _validate_upload_type(object_key, content_type)
        target_folder_id = await self._ensure_path_folder(bucket_name, object_key)
        if await self._find_file(bucket_name, object_key):
            raise ValueError("File already exists")

        media = self.MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=_normalize_content_type(content_type) or "application/octet-stream",
            resumable=False,
        )
        body = {
            "name": Path(object_key).name,
            "parents": [target_folder_id],
        }
        response = await self._execute(
            self._service.files().create(
                body=body,
                media_body=media,
                fields="id,name,mimeType,size,modifiedTime",
                supportsAllDrives=True,
            )
        )
        return object_key

    async def download_file(self, bucket_name: str, object_key: str) -> bytes:
        file = await self._find_file(bucket_name, object_key)
        if not file:
            raise ValueError("Google Drive file not found")

        self._download_metadata[(bucket_name, object_key)] = file

        request = self._service.files().get_media(fileId=file["id"], supportsAllDrives=True)
        fh = io.BytesIO()
        downloader = self.MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = await asyncio.to_thread(downloader.next_chunk)
        fh.seek(0)
        return fh.read()

    async def get_file_url(self, bucket_name: str, object_key: str) -> str:
        return self._build_proxy_download_url(bucket_name, object_key)

    async def create_upload_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        raise ValueError(
            "Signed upload URLs are not supported for Google Drive. "
            "Use the authenticated /api/v1/storage/upload endpoint instead."
        )

    async def create_download_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        await self.get_object_info(ObjectRequest(bucket_name=request.bucket_name, object_key=request.object_key))
        return FileUpDownResponse(
            download_url=self._build_proxy_download_url(request.bucket_name, request.object_key),
            expires_at=self._expires_at(hours=1),
        )


class StorageService(StorageServiceBase):
    def __init__(self):
        if getattr(settings, "google_drive_enabled", False):
            self._impl = GoogleDriveStorageService()
        else:
            self._impl = SupabaseStorageService()

    async def create_bucket(self, request: BucketRequest) -> BucketResponse:
        return await self._impl.create_bucket(request)

    async def list_buckets(self) -> BucketListResponse:
        return await self._impl.list_buckets()

    async def list_objects(self, request: OSSBaseModel) -> ObjectListResponse:
        return await self._impl.list_objects(request)

    async def get_object_info(self, request: ObjectRequest) -> ObjectInfo:
        return await self._impl.get_object_info(request)

    async def rename_object(self, request: RenameRequest) -> RenameResponse:
        return await self._impl.rename_object(request)

    async def delete_object(self, request: ObjectRequest) -> DeleteResponse:
        return await self._impl.delete_object(request)

    async def upload_file(
        self,
        bucket_name: str,
        object_key: str,
        file_bytes: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        return await self._impl.upload_file(bucket_name, object_key, file_bytes, content_type)

    async def download_file(self, bucket_name: str, object_key: str) -> bytes:
        return await self._impl.download_file(bucket_name, object_key)

    async def get_file_url(self, bucket_name: str, object_key: str) -> str:
        return await self._impl.get_file_url(bucket_name, object_key)

    async def get_file_metadata(self, bucket_name: str, object_key: str) -> dict[str, Any]:
        return await self._impl.get_file_metadata(bucket_name, object_key)

    async def create_upload_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        return await self._impl.create_upload_url(request)

    async def create_download_url(self, request: FileUpDownRequest) -> FileUpDownResponse:
        return await self._impl.create_download_url(request)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._impl, name)
