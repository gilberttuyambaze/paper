"""Factory for creating and selecting configured OCR providers."""

from __future__ import annotations

import logging
import os
from typing import Any

from core.config import settings
from services.ocr.base import DocumentOCRProvider
from services.ocr.local_provider import LocalOCRProvider
from services.ocr.vision_provider import VisionAIOCRProvider

logger = logging.getLogger(__name__)


class OCRProviderFactory:
    """Creates the appropriate OCR provider based on configuration and system availability."""

    @classmethod
    async def get_provider(cls, preferred: str | None = None) -> DocumentOCRProvider:
        mode = (preferred or os.getenv("OCR_PROVIDER", "auto")).strip().lower()

        local_prov = LocalOCRProvider()
        local_available = await local_prov.is_available()

        vision_prov = VisionAIOCRProvider()
        vision_available = await vision_prov.is_available()

        if mode == "local" and local_available:
            return local_prov
        elif mode == "vision" and vision_available:
            return vision_prov
        elif mode == "local" and not local_available and vision_available:
            logger.info("Local OCR requested but not available; falling back to Vision AI OCR.")
            return vision_prov

        # Auto mode: prefer local if available, else vision
        if local_available:
            return local_prov
        elif vision_available:
            return vision_prov

        # Fallback to local (which will safely report unavailability per page)
        return local_prov


async def get_ocr_provider(preferred: str | None = None) -> DocumentOCRProvider:
    return await OCRProviderFactory.get_provider(preferred)
