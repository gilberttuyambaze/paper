"""Local OCR provider implementation using RapidOCR ONNX or system Tesseract."""

from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
from typing import Any

from services.ocr.base import DocumentOCRProvider, OCRBlock, OCRPageResult
from services.ocr.rapid_provider import RapidOCRProvider

logger = logging.getLogger(__name__)


class LocalOCRProvider:
    """Executes local OCR using RapidOCR (preferred, standalone) or Tesseract CLI fallback."""

    name: str = "local_ocr"

    def __init__(self, tesseract_cmd: str | None = None, engine: str = "auto"):
        self.explicit_tesseract = tesseract_cmd is not None
        self.tesseract_cmd = tesseract_cmd or shutil.which("tesseract")
        self.engine = engine
        self._rapid = RapidOCRProvider()

    async def is_available(self) -> bool:
        if self.explicit_tesseract or self.engine == "tesseract":
            return bool(self.tesseract_cmd)
        if await self._rapid.is_available():
            return True
        return bool(self.tesseract_cmd)

    def _run_tesseract(self, image_bytes: bytes, page_number: int) -> OCRPageResult:
        if not self.tesseract_cmd:
            return OCRPageResult(
                page_number=page_number,
                text="",
                confidence=0.0,
                blocks=[],
                provider=self.name,
                is_scanned=True,
                metadata={"error": "tesseract binary not installed on system"},
            )

        try:
            proc = subprocess.run(
                [self.tesseract_cmd, "stdin", "stdout", "--oem", "1", "-l", "eng"],
                input=image_bytes,
                capture_output=True,
                timeout=15,
                check=False,
            )
            raw_text = proc.stdout.decode("utf-8", errors="replace").strip()
            confidence = 0.85 if len(raw_text) > 40 else 0.30

            blocks = []
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
            for p in paragraphs:
                q_match = re.match(r"^(?:question|q\.?|problem)\s*(\d+(?:\s*\([a-z0-9]+\))?)\b", p, re.IGNORECASE)
                q_num = q_match.group(1) if q_match else None
                b_type = "question" if q_num else "paragraph"
                blocks.append(OCRBlock(text=p, block_type=b_type, confidence=confidence, question_number=q_num))

            return OCRPageResult(
                page_number=page_number,
                text=raw_text,
                confidence=confidence,
                blocks=blocks,
                provider=self.name,
                is_scanned=True,
                metadata={"exit_code": proc.returncode},
            )
        except Exception as exc:
            logger.warning("Local tesseract OCR failed on page %s: %s", page_number, exc)
            return OCRPageResult(
                page_number=page_number,
                text="",
                confidence=0.0,
                blocks=[],
                provider=self.name,
                is_scanned=True,
                metadata={"error": str(exc)},
            )

    async def extract_page(
        self,
        image_bytes: bytes,
        page_number: int,
        *,
        context_hint: str | None = None,
    ) -> OCRPageResult:
        # If tesseract was explicitly requested/passed, run tesseract
        if (self.explicit_tesseract or self.engine == "tesseract") and self.tesseract_cmd:
            return self._run_tesseract(image_bytes, page_number)

        # Otherwise prefer RapidOCR
        if await self._rapid.is_available():
            res = await self._rapid.extract_page(image_bytes, page_number, context_hint=context_hint)
            if res.text.strip():
                return res
            if self.tesseract_cmd:
                return self._run_tesseract(image_bytes, page_number)
            return res

        if self.tesseract_cmd:
            return self._run_tesseract(image_bytes, page_number)

        return OCRPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            blocks=[],
            provider=self.name,
            is_scanned=True,
            metadata={"error": "Neither rapidocr-onnxruntime nor tesseract binary is available on system"},
        )
