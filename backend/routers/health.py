from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.database import check_database_health
from services.site_access import get_site_settings

router = APIRouter(prefix="/health", tags=["database"])


@router.get("/site-access")
async def site_access_status(db: AsyncSession = Depends(get_db)):
    settings = await get_site_settings(db)
    return {"maintenance_mode": bool(settings.maintenance_mode), "maintenance_message": settings.maintenance_message}


@router.get("/database")
async def database_health():
    is_healthy = await check_database_health()
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "service": "database",
    }
