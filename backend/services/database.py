import logging
import os
import time

from core.database import db_manager
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def check_database_health() -> bool:
    """Check if database is healthy"""
    start_time = time.time()
    logger.debug("[DB_OP] Starting database health check")
    try:
        if not db_manager.async_session_maker:
            return False

        async with db_manager.async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            logger.debug(f"[DB_OP] Database health check completed in {time.time() - start_time:.4f}s - healthy: True")
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        logger.debug(f"[DB_OP] Database health check failed in {time.time() - start_time:.4f}s - healthy: False")
        return False


async def initialize_database():
    """Initialize database and create tables"""
    if "URHUD_IGNORE_INIT_DB" in os.environ:
        logger.info("Ignore creating tables")
        return
    start_time = time.time()
    logger.debug("[DB_OP] Starting database initialization")
    try:
        logger.info("Starting database initialization...")
        await db_manager.init_db()
        auto_create_tables = os.getenv("URHUD_AUTO_CREATE_TABLES", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        schema_checks_on_startup = os.getenv("URHUD_SCHEMA_CHECKS_ON_STARTUP", "true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        if schema_checks_on_startup:
            logger.info("Checking existing schema for required auth/profile, site settings, and storage metadata columns...")
            await db_manager.ensure_tables_exist_for_models(
                "paper_interactions",
                "system_health_heartbeats",
                "site_settings",
                "academic_programme_submissions",
                "academic_programme_aliases",
            )
            tables_to_sync = [
                "site_settings",
                "users",
                "user_profiles",
                "papers",
                "solutions",
                "comments",
                "books",
                "reports",
                "notifications",
                "system_health_heartbeats",
                "academic_programme_submissions",
                "academic_programme_aliases",
            ]
            await db_manager.ensure_model_columns_for_existing_tables(*tables_to_sync)
        else:
            logger.info("Skipping schema checks during normal startup; enable URHUD_SCHEMA_CHECKS_ON_STARTUP to run them.")
        if auto_create_tables:
            logger.info("Auto table creation enabled; creating tables if they do not exist...")
            await db_manager.create_tables()
            logger.info("Table creation completed")
        else:
            logger.info("Skipping automatic table creation; existing tables were still checked for missing columns")
        logger.info("Database initialized successfully")
        logger.debug(f"[DB_OP] Database initialization completed in {time.time() - start_time:.4f}s")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise



async def close_database():
    """Close database connections"""
    start_time = time.time()
    logger.debug("[DB_OP] Starting database close")
    try:
        await db_manager.close_db()
        logger.info("Database connections closed")
        logger.debug(f"[DB_OP] Database close completed in {time.time() - start_time:.4f}s")
    except Exception as e:
        logger.error(f"Error closing database: {e}")
        logger.debug(f"[DB_OP] Database close failed in {time.time() - start_time:.4f}s")
