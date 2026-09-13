"""Image extraction, validation, rendering, and preprocessing for scanned PDF pages."""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


def render_pdf_page_to_bytes(pdf_bytes: bytes, page_number: int, scale: float = 2.0) -> bytes | None:
    """Renders a specific page of a PDF document directly to high-resolution PNG image bytes.
    
    Args:
        pdf_bytes: Raw binary bytes of the PDF file.
        page_number: 1-indexed page number.
        scale: Resolution scale factor (2.0 gives ~144-200 DPI).
    """
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(pdf_bytes)
        if page_number < 1 or page_number > len(doc):
            return None

        page = doc[page_number - 1]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()

        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except Exception as exc:
        logger.debug("pypdfium2 rendering failed for page %s: %s", page_number, exc)
        return None


def extract_page_image_bytes(page_obj: Any) -> bytes | None:
    """Extract raw image bytes from a pypdf page object if present."""
    try:
        if hasattr(page_obj, "images") and page_obj.images:
            # Sort by data size descending to pick the main full-page scan
            images = list(page_obj.images)
            if images:
                best_img = max(images, key=lambda img: len(getattr(img, "data", b"")))
                data = getattr(best_img, "data", None)
                if data and len(data) > 2048:
                    return bytes(data)
    except Exception as exc:
        logger.debug("Failed extracting image from pypdf page: %s", exc)
    return None


def detect_image_mime_type(image_bytes: bytes) -> str:
    """Detect image MIME type from magic header bytes."""
    if not image_bytes:
        return "application/octet-stream"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    if image_bytes.startswith(b"%PDF"):
        return "application/pdf"
    return "image/jpeg"


def to_data_uri(image_bytes: bytes) -> str:
    """Convert raw image bytes to an inline data URI."""
    mime = detect_image_mime_type(image_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"
