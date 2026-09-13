"""Abstract base protocols and dataclasses for document OCR providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class OCRBlock:
    text: str
    block_type: str = "paragraph"  # "heading" | "question" | "subquestion" | "table" | "formula" | "paragraph"
    confidence: float = 1.0
    bounding_box: list[float] | None = None  # [x0, y0, x1, y1] normalized (0.0 to 1.0)
    question_number: str | None = None
    subquestion_number: str | None = None
    section_title: str | None = None


@dataclass
class OCRPageResult:
    page_number: int
    text: str
    confidence: float  # 0.0 to 1.0
    blocks: list[OCRBlock] = field(default_factory=list)
    provider: str = "unknown"
    detected_language: str | None = None
    is_scanned: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DocumentOCRProvider(Protocol):
    """Protocol for document optical character recognition engines."""

    name: str

    async def is_available(self) -> bool:
        """Check whether the OCR engine is available and healthy."""
        ...

    async def extract_page(
        self,
        image_bytes: bytes,
        page_number: int,
        *,
        context_hint: str | None = None,
    ) -> OCRPageResult:
        """Extract structured text and blocks from page image bytes."""
        ...
