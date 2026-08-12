import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.solutions import Solutions
from services.storage import StorageService

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class SolutionsService:
    """Service layer for Solutions operations"""

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
                data["drive_file_id"] = metadata.get("drive_file_id")
                data["storage_provider"] = metadata.get("storage_provider")
                data["file_name"] = metadata.get("file_name")
                data["file_size"] = metadata.get("file_size")
                data["mime_type"] = metadata.get("mime_type")
            except Exception as exc:
                logger.warning("Could not attach file metadata for solution file_key=%s: %s", data.get("file_key"), exc)

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Solutions]:
        """Create a new solutions"""
        try:
            if user_id:
                data['user_id'] = user_id
            await self._attach_storage_metadata(data)
            obj = Solutions(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created solutions with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating solutions: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for solutions {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Solutions]:
        """Get solutions by ID (user can only see their own records)"""
        try:
            query = select(Solutions).where(Solutions.id == obj_id)
            if user_id:
                query = query.where(Solutions.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching solutions {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of solutionss (user can only see their own records)"""
        try:
            query = select(Solutions)
            count_query = select(func.count(Solutions.id))
            
            if user_id:
                query = query.where(Solutions.user_id == user_id)
                count_query = count_query.where(Solutions.user_id == user_id)
            
            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Solutions, field):
                        query = query.where(getattr(Solutions, field) == value)
                        count_query = count_query.where(getattr(Solutions, field) == value)
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Solutions, field_name):
                        query = query.order_by(getattr(Solutions, field_name).desc())
                else:
                    if hasattr(Solutions, sort):
                        query = query.order_by(getattr(Solutions, sort))
            else:
                query = query.order_by(Solutions.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching solutions list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Solutions]:
        """Update solutions (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Solutions {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated solutions {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating solutions {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete solutions (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Solutions {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted solutions {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting solutions {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Solutions]:
        """Get solutions by any field"""
        try:
            if not hasattr(Solutions, field_name):
                raise ValueError(f"Field {field_name} does not exist on Solutions")
            result = await self.db.execute(
                select(Solutions).where(getattr(Solutions, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching solutions by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Solutions]:
        """Get list of solutionss filtered by field"""
        try:
            if not hasattr(Solutions, field_name):
                raise ValueError(f"Field {field_name} does not exist on Solutions")
            result = await self.db.execute(
                select(Solutions)
                .where(getattr(Solutions, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Solutions.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching solutionss by {field_name}: {str(e)}")
            raise