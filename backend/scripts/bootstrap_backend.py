import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("URHUD_AUTO_CREATE_TABLES", "true")

import main  # noqa: F401
from services.auth import initialize_admin_user
from services.database import close_database, initialize_database


async def bootstrap() -> None:
    await initialize_database()
    await initialize_admin_user()
    await close_database()


if __name__ == "__main__":
    asyncio.run(bootstrap())
