"""Vision AI OCR provider using configured vision-capable LLM models."""

from __future__ import annotations

import logging
import re
from typing import Any

from core.config import settings
from services.ai.base import AIGenerationRequest, AIMessage
from services.ai.service import AIService, AIProviderFactory
from services.ocr.base import DocumentOCRProvider, OCRBlock, OCRPageResult
from services.ocr.image_preprocessor import to_data_uri

logger = logging.getLogger(__name__)


class VisionAIOCRProvider:
    """Uses a vision-capable AI provider (Gemini, OpenAI, OpenRouter, etc.) for high-fidelity OCR."""

    name: str = "vision_ai"

    async def is_available(self) -> bool:
        return AIService.is_configured()

    async def extract_page(
        self,
        image_bytes: bytes,
        page_number: int,
        *,
        context_hint: str | None = None,
    ) -> OCRPageResult:
        if not image_bytes or not AIService.is_configured():
            return OCRPageResult(
                page_number=page_number,
                text="",
                confidence=0.0,
                blocks=[],
                provider=self.name,
                is_scanned=True,
                metadata={"error": "Vision AI is not configured or image is empty"},
            )

        data_uri = to_data_uri(image_bytes)

        system_instruction = (
            "You are a high-precision academic document OCR and layout transcriber.\n"
            "Your sole task is to transcribe all text from this academic examination page image with absolute fidelity.\n\n"
            "Rules:\n"
            "1. Transcribe all text, headings, sections (e.g. SECTION A), question numbers (e.g. Question 1, 1., Q1), and sub-parts (e.g. (a), (b), (i)) EXACTLY as written.\n"
            "2. Preserve mathematical equations, formulas, Greek letters, and fractions using standard LaTeX (e.g. $E = mc^2$, $\\int_0^1 x dx$).\n"
            "3. Preserve tables and tabular data using Markdown table format.\n"
            "4. NEVER invent or assume questions, answers, or text that is not visible on the page image.\n"
            "5. If a word or formula is illegible/smudged, output [unreadable] instead of guessing.\n"
            "6. Output ONLY the extracted text and transcription without conversational commentary."
        )

        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"Transcribe page {page_number} of this academic examination paper precisely." + (f" Context hint: {context_hint}" if context_hint else ""),
            },
            {
                "type": "image_url",
                "image_url": {"url": data_uri},
            },
        ]

        messages = [
            AIMessage(role="system", content=system_instruction),
            AIMessage(role="user", content=user_content),
        ]

        req = AIGenerationRequest(
            temperature=0.0,
            max_output_tokens=min(settings.ai_max_output_tokens, 3000),
            messages=messages,
            user_id="ocr_ingestion",
        )

        try:
            # Waterfall attempts best vision-capable provider
            ai_service = AIService()
            response = await ai_service.generate_with_waterfall(req, per_provider_timeout=18.0)
            text = response.content.strip()

            blocks: list[OCRBlock] = []
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            current_section: str | None = None

            for p in paragraphs:
                sec_match = re.match(r"^(?:##?\s*)?(SECTION\s+[A-Z0-9]+|PART\s+[A-Z0-9]+|MODULE\s+[A-Z0-9]+)\b", p, re.IGNORECASE)
                if sec_match:
                    current_section = sec_match.group(1).upper()
                    blocks.append(OCRBlock(text=p, block_type="heading", confidence=0.95, section_title=current_section))
                    continue

                q_match = re.match(r"^(?:(?:##?\s*)?(?:Question|Q\.?|Problem)\s*(\d+)|(\d+)\.\s+)", p, re.IGNORECASE)
                q_num = (q_match.group(1) or q_match.group(2)) if q_match else None
                b_type = "question" if q_num else "paragraph"
                blocks.append(OCRBlock(text=p, block_type=b_type, confidence=0.92, question_number=q_num, section_title=current_section))

            confidence = 0.92 if len(text) > 50 else (0.40 if text else 0.0)

            return OCRPageResult(
                page_number=page_number,
                text=text,
                confidence=confidence,
                blocks=blocks,
                provider=f"vision_ai:{response.provider}:{response.model}",
                is_scanned=True,
                metadata={"duration_ms": response.duration_ms, "model": response.model},
            )
        except Exception as exc:
            logger.warning("Vision AI OCR failed on page %s: %s", page_number, exc)
            return OCRPageResult(
                page_number=page_number,
                text="",
                confidence=0.0,
                blocks=[],
                provider=self.name,
                is_scanned=True,
                metadata={"error": str(exc)},
            )
