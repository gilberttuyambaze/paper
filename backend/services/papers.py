import logging
from typing import Optional, Dict, Any, List

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.comments import Comments
from models.paper_interactions import PaperInteractions
from models.papers import PaperPassage, PaperQuestion, QuestionAttempt, QuestionClassification, QuestionTopic, Papers
from models.paper_processing import PaperProcessingJob
from models.reports import Reports
from models.solutions import Solutions
from services.storage import StorageService
from services.paper_processing import PaperProcessingService
from services.contribution_communications import record_contribution_event
from schemas.storage import ObjectRequest

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class PapersService:
    """Service layer for Papers operations"""

    DEFAULT_STORAGE_BUCKET = "papers"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _attach_storage_metadata(self, data: Dict[str, Any]) -> None:
        if not data:
            return

        storage = StorageService()

        if data.get("file_key"):
            try:
                metadata = await storage.get_file_metadata(self.DEFAULT_STORAGE_BUCKET, data["file_key"])
                data["file_drive_file_id"] = metadata.get("drive_file_id")
                data["file_storage_provider"] = metadata.get("storage_provider")
                data["file_name"] = metadata.get("file_name")
                data["file_size"] = metadata.get("file_size")
                data["file_mime_type"] = metadata.get("mime_type")
            except Exception as exc:
                logger.warning("Could not attach file metadata for paper file_key=%s: %s", data.get("file_key"), exc)

        if data.get("cover_key"):
            try:
                metadata = await storage.get_file_metadata(self.DEFAULT_STORAGE_BUCKET, data["cover_key"])
                data["cover_drive_file_id"] = metadata.get("drive_file_id")
                data["cover_storage_provider"] = metadata.get("storage_provider")
                data["cover_file_name"] = metadata.get("file_name")
                data["cover_file_size"] = metadata.get("file_size")
                data["cover_mime_type"] = metadata.get("mime_type")
            except Exception as exc:
                logger.warning("Could not attach cover metadata for paper file_key=%s: %s", data.get("cover_key"), exc)

        if data.get("solution_key"):
            try:
                metadata = await storage.get_file_metadata(self.DEFAULT_STORAGE_BUCKET, data["solution_key"])
                data["solution_drive_file_id"] = metadata.get("drive_file_id")
                data["solution_storage_provider"] = metadata.get("storage_provider")
                data["solution_file_name"] = metadata.get("file_name")
                data["solution_file_size"] = metadata.get("file_size")
                data["solution_mime_type"] = metadata.get("mime_type")
            except Exception as exc:
                logger.warning("Could not attach solution metadata for paper solution_key=%s: %s", data.get("solution_key"), exc)

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Papers]:
        """Create a new papers"""
        try:
            if user_id:
                data['user_id'] = user_id
            await self._attach_storage_metadata(data)
            # Receipt is deliberately small and durable. Expensive OCR/indexing
            # is performed only by the separate paper-processing worker.
            data.setdefault("extraction_status", "RECEIVED")
            obj = Papers(**data)
            self.db.add(obj)
            await self.db.flush()
            await PaperProcessingService(self.db).enqueue(obj)
            await record_contribution_event(
                self.db, event_type="PAPER_RECEIVED", paper=obj, user_id=str(obj.user_id)
            )
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created papers with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating papers: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for papers {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Papers]:
        """Get papers by ID (user can only see their own records)"""
        try:
            query = select(Papers).where(Papers.id == obj_id)
            if user_id:
                query = query.where(Papers.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching papers {obj_id}: {str(e)}")
            raise

    async def get_list(
        self,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of paperss (user can only see their own records)"""
        try:
            query = select(Papers)
            count_query = select(func.count(Papers.id))

            if user_id:
                query = query.where(Papers.user_id == user_id)
                count_query = count_query.where(Papers.user_id == user_id)

            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Papers, field):
                        query = query.where(getattr(Papers, field) == value)
                        count_query = count_query.where(getattr(Papers, field) == value)

            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Papers, field_name):
                        query = query.order_by(getattr(Papers, field_name).desc())
                else:
                    if hasattr(Papers, sort):
                        query = query.order_by(getattr(Papers, sort))
            else:
                query = query.order_by(Papers.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching papers list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Papers]:
        """Update papers (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Papers {obj_id} not found for update")
                return None
            old_file_key = getattr(obj, "file_key", None)
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)

            # File replacement queues a durable reprocessing run; it must not
            # hold an HTTP request open for OCR or embeddings.
            if obj.file_key and (obj.file_key != old_file_key or update_data.get("extraction_status") == "pending"):
                await PaperProcessingService(self.db).retry(obj.id)

            logger.info(f"Updated papers {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating papers {obj_id}: {str(e)}")
            raise

    async def _cleanup_drive_files(self, paper: Papers, solutions: list[Solutions]) -> None:
        """Permanently delete associated Google Drive files.

        Treats already-missing files as success (no error if file already gone).
        Raises HTTPException if deletion genuinely fails.
        """
        storage = StorageService()
        files_to_delete = [
            (paper.file_key, paper.file_drive_file_id, "PDF"),
            (paper.cover_key, paper.cover_drive_file_id, "Cover"),
            (paper.solution_key, paper.solution_drive_file_id, "Solution"),
        ]
        files_to_delete.extend((solution.file_key, solution.drive_file_id, "Solution attachment") for solution in solutions)

        for object_key, drive_file_id, file_type in files_to_delete:
            if not object_key and not drive_file_id:
                continue

            try:
                if drive_file_id:
                    try:
                        await storage.delete_object_by_id(self.DEFAULT_STORAGE_BUCKET, object_key or "", drive_file_id)
                        logger.info("Deleted Paper %s %s from Drive: provider_id=%s", paper.id, file_type, drive_file_id)
                    except ValueError as e:
                        if "not found" in str(e).lower():
                            logger.info(f"Paper {paper.id} {file_type} already absent from Drive")
                        else:
                            raise
                elif object_key:
                    request = ObjectRequest(
                        bucket_name=self.DEFAULT_STORAGE_BUCKET,
                        object_key=object_key
                    )
                    try:
                        await storage.delete_object(request)
                        logger.info(f"Deleted Paper {paper.id} {file_type} from Drive: key={object_key}")
                    except ValueError as e:
                        if "not found" in str(e).lower():
                            logger.info(f"Paper {paper.id} {file_type} already absent from Drive")
                        else:
                            raise
            except Exception as e:
                logger.error(f"Error deleting Paper {paper.id} {file_type} from Drive: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete Paper files from storage: {str(e)}"
                )

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Hard delete papers and associated Google Drive files.

        Authorization must be checked by caller. This method does not re-check user_id.
        """
        try:
            obj = await self.db.get(Papers, obj_id)
            if not obj:
                logger.warning(f"Papers {obj_id} not found for deletion")
                return False

            solutions = (await self.db.execute(select(Solutions).where(Solutions.paper_id == obj_id))).scalars().all()
            await self._cleanup_drive_files(obj, solutions)

            question_ids = select(PaperQuestion.id).where(PaperQuestion.paper_id == obj_id)
            await self.db.execute(delete(QuestionTopic).where(QuestionTopic.question_id.in_(question_ids)))
            await self.db.execute(delete(QuestionClassification).where(QuestionClassification.question_id.in_(question_ids)))
            await self.db.execute(delete(QuestionAttempt).where(QuestionAttempt.question_id.in_(question_ids)))
            await self.db.execute(delete(PaperQuestion).where(PaperQuestion.paper_id == obj_id))
            await self.db.execute(delete(PaperPassage).where(PaperPassage.paper_id == obj_id))
            await self.db.execute(delete(PaperProcessingJob).where(PaperProcessingJob.paper_id == obj_id))
            await self.db.execute(delete(Solutions).where(Solutions.paper_id == obj_id))
            await self.db.execute(delete(Comments).where(Comments.paper_id == obj_id))
            await self.db.execute(delete(PaperInteractions).where(PaperInteractions.paper_id == obj_id))
            await self.db.execute(delete(Reports).where(Reports.paper_id == obj_id))

            # Now delete the database record
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Hard deleted papers {obj_id}")
            return True
        except HTTPException:
            # Re-raise HTTP exceptions (storage failures should surface to caller)
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting papers {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Papers]:
        """Get papers by any field"""
        try:
            if not hasattr(Papers, field_name):
                raise ValueError(f"Field {field_name} does not exist on Papers")
            result = await self.db.execute(
                select(Papers).where(getattr(Papers, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching papers by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Papers]:
        """Get list of paperss filtered by field"""
        try:
            if not hasattr(Papers, field_name):
                raise ValueError(f"Field {field_name} does not exist on Papers")
            result = await self.db.execute(
                select(Papers)
                .where(getattr(Papers, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Papers.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching paperss by {field_name}: {str(e)}")
            raise
