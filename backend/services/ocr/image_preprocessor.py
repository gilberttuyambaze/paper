"""Image extraction, validation, rendering, and preprocessing for scanned PDF pages."""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PdfPageRenderer:
    """Keep one PDFium document open for a single ingestion run.

    The old helper opened and reparsed the full PDF for every scanned page.
    On image-heavy papers that repeated parsing dominated rendering time.
    """

    def __init__(self, pdf_bytes: bytes):
        self._doc = None
        try:
            import pypdfium2 as pdfium
            self._doc = pdfium.PdfDocument(pdf_bytes)
        except Exception as exc:
            logger.debug("pypdfium2 document initialization failed: %s", exc)

    def render(self, page_number: int, scale: float = 2.0) -> bytes | None:
        if self._doc is None or page_number < 1:
            return None
        try:
            # Some malformed/encrypted PDFs leave PDFium with a document
            # handle but no page-count value. Do not let that optional render
            # path abort the whole ingestion job; pypdf embedded-image/native
            # extraction below can still recover the page.
            page_count = len(self._doc)
            if not isinstance(page_count, int) or page_number > page_count:
                return None
            page = self._doc[page_number - 1]
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
        except Exception as exc:
            logger.debug("pypdfium2 rendering failed for page %s: %s", page_number, exc)
            return None

    def close(self) -> None:
        """Release PDFium resources promptly after this ingestion run."""
        document, self._doc = self._doc, None
        if document is not None:
            try:
                document.close()
            except Exception:
                # Some PDFium builds release this object during GC instead.
                pass

    def __del__(self) -> None:
        # The normal ingestion path closes explicitly. This protects an
        # exceptional path before that point without relying on PDFium GC.
        self.close()


def render_pdf_page_to_bytes(pdf_bytes: bytes, page_number: int, scale: float = 2.0) -> bytes | None:
    """Renders a specific page of a PDF document directly to high-resolution PNG image bytes.
    
    Args:
        pdf_bytes: Raw binary bytes of the PDF file.
        page_number: 1-indexed page number.
        scale: Resolution scale factor (2.0 gives ~144-200 DPI).
    """
    return PdfPageRenderer(pdf_bytes).render(page_number, scale)


def extract_page_image_bytes(page_obj: Any) -> bytes | None:
    """Extract raw image bytes from a pypdf page object if present."""
    try:
        if hasattr(page_obj, "images") and page_obj.images:
            # Sort by data size descending to pick the main full-page scan
            images = list(page_obj.images)
            if images:
                # pypdf can expose an image entry without decoded bytes for a
                # damaged/masked XObject. Treat it as unavailable rather than
                # allowing ``len(None)`` to fail the entire paper run.
                best_img = max(images, key=lambda img: len(getattr(img, "data", None) or b""))
                data = getattr(best_img, "data", None) or b""
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
