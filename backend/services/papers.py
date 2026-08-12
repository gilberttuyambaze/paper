import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.papers import Papers
from services.storage import StorageService

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
            obj = Papers(**data)
            self.db.add(obj)
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
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated papers {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating papers {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete papers (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Papers {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted papers {obj_id}")
            return True
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