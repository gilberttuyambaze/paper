"""High-performance local OCR provider using RapidOCR and ONNX Runtime.

Runs standalone without requiring external system tesseract binaries or internet calls.
Preserves page geometry, coordinates, and reading order.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from services.ocr.base import DocumentOCRProvider, OCRBlock, OCRPageResult

logger = logging.getLogger(__name__)

# Global cached engine to avoid redundant ONNX model initialization overhead
_rapid_engine = None
_rapid_init_lock = asyncio.Lock()


def _get_engine():
    global _rapid_engine
    if _rapid_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapid_engine = RapidOCR()
        except Exception as exc:
            logger.warning("Failed to initialize RapidOCR engine: %s", exc)
            _rapid_engine = None
    return _rapid_engine


def clean_ocr_text(text: str) -> str:
    """Cleans common OCR artifacts, restores missing spaces, and fixes fused punctuation."""
    if not text:
        return ""

    known_phrases = {
        "COLLEGEOFSCIENCEANDTECHNOLOGY": "COLLEGE OF SCIENCE AND TECHNOLOGY",
        "COLLEGEOFSCIENCE": "COLLEGE OF SCIENCE",
        "UNIVERSITYOT": "UNIVERSITY OF",
        "CENTREFORLANGUAGEENHANCEMENT": "CENTRE FOR LANGUAGE ENHANCEMENT",
        "ENGLISHFORGENERALPURPOSES": "ENGLISH FOR GENERAL PURPOSES",
        "ENDOFSEMESTER2EXAMINATION": "END OF SEMESTER 2 EXAMINATION",
        "ENDOFSEMESTER1EXAMINATION": "END OF SEMESTER 1 EXAMINATION",
        "ACADEMICYEAR": "ACADEMIC YEAR",
        "LEVELOFSTUDY": "LEVEL OF STUDY",
        "MODULEWEIGHTING": "MODULE WEIGHTING",
        "MAXIMUMMARKS": "MAXIMUM MARKS",
        "allof the given answers": "all of the given answers",
    }
    for k, v in known_phrases.items():
        text = text.replace(k, v)

    # Space after period or closing paren before uppercase letter
    text = re.sub(r"([a-zA-Z0-9\)])\.([A-Z])", r"\1. \2", text)
    # Space between lowercase and uppercase if fused (e.g. "step.They" or "abilities,making")
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r",([a-zA-Z])", r", \1", text)
    text = re.sub(r":([a-zA-Z0-9])", r": \1", text)
    # Marks pattern
    text = re.sub(r"(\d+)\/(\d+)\s*(mks|marks)\b", r"\1/\2 \3", text, flags=re.IGNORECASE)
    text = re.sub(r"\/(\d+)\s*(mks|marks)\b", r"/\1 \2", text, flags=re.IGNORECASE)
    # Normalize multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _process_ocr_boxes_sync(image_bytes: bytes, page_number: int) -> OCRPageResult:
    """Synchronous worker that runs RapidOCR model inference on image bytes."""
    engine = _get_engine()
    if engine is None:
        return OCRPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            blocks=[],
            provider="rapid_ocr",
            is_scanned=True,
            metadata={"error": "rapidocr_onnxruntime is not installed or failed to initialize"},
        )

    try:
        results, elapse = engine(image_bytes)
    except Exception as exc:
        logger.warning("RapidOCR execution failed on page %s: %s", page_number, exc)
        return OCRPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            blocks=[],
            provider="rapid_ocr",
            is_scanned=True,
            metadata={"error": str(exc)},
        )

    if not results:
        return OCRPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            blocks=[],
            provider="rapid_ocr",
            is_scanned=True,
            metadata={"duration_s": sum(elapse) if isinstance(elapse, (list, tuple)) else elapse},
        )

    # Group boxes into reading order (cluster lines by Y coordinates, sort left to right by X)
    # Each item: [box, text, score] where box is [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
    boxes_with_info = []
    for item in results:
        box, text, score = item[0], item[1], float(item[2])
        cleaned = clean_ocr_text(text)
        if not cleaned:
            continue
        # Bounding box coordinates
        x_coords = [p[0] for p in box]
        y_coords = [p[1] for p in box]
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        center_y = (min_y + max_y) / 2.0
        height = max(1.0, max_y - min_y)
        boxes_with_info.append({
            "box": box,
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "center_y": center_y,
            "height": height,
            "text": cleaned,
            "score": score,
        })

    # Sort primarily by min_y
    boxes_with_info.sort(key=lambda b: b["min_y"])

    # Line clustering
    lines: list[list[dict[str, Any]]] = []
    for b in boxes_with_info:
        placed = False
        for line in lines:
            # Check vertical overlap with line elements
            line_avg_y = sum(item["center_y"] for item in line) / len(line)
            line_avg_h = sum(item["height"] for item in line) / len(line)
            if abs(b["center_y"] - line_avg_y) <= max(12.0, line_avg_h * 0.65):
                line.append(b)
                placed = True
                break
        if not placed:
            lines.append([b])

    # Within each line, sort left-to-right by min_x
    formatted_lines: list[str] = []
    total_score = 0.0
    total_count = 0

    for line in lines:
        line.sort(key=lambda item: item["min_x"])
        line_text = " ".join(item["text"] for item in line)
        formatted_lines.append(line_text)
        for item in line:
            total_score += item["score"]
            total_count += 1

    full_text = "\n".join(formatted_lines).strip()
    avg_conf = (total_score / max(1, total_count)) if total_count > 0 else 0.0

    # Parse into structured blocks
    blocks: list[OCRBlock] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-Z0-9\(\[])", full_text) if p.strip()]
    current_section: str | None = None

    for p in paragraphs:
        sec_match = re.match(r"^(?:##?\s*)?(SECTION\s+[A-Z0-9]+|PART\s+[A-Z0-9]+|MODULE\s+[A-Z0-9]+)\b", p, re.IGNORECASE)
        if sec_match:
            current_section = sec_match.group(1).upper()
            blocks.append(OCRBlock(text=p, block_type="heading", confidence=avg_conf, section_title=current_section))
            continue

        q_match = re.match(r"^(?:(?:##?\s*)?(?:Question|Q\.?|Problem)\s*(\d+[a-z]?)|(\d+)\.\s+|(\d+)\)\s+)", p, re.IGNORECASE)
        q_num = (q_match.group(1) or q_match.group(2) or q_match.group(3)) if q_match else None
        b_type = "question" if q_num else "paragraph"
        blocks.append(OCRBlock(text=p, block_type=b_type, confidence=avg_conf, question_number=q_num, section_title=current_section))

    return OCRPageResult(
        page_number=page_number,
        text=full_text,
        confidence=round(avg_conf, 2),
        blocks=blocks,
        provider="rapid_ocr",
        is_scanned=True,
        metadata={"box_count": total_count, "line_count": len(lines)},
    )


class RapidOCRProvider:
    """Local OCR provider using RapidOCR with ONNX Runtime."""

    name: str = "rapid_ocr"

    async def is_available(self) -> bool:
        try:
            import rapidocr_onnxruntime
            return True
        except ImportError:
            return False

    async def extract_page(
        self,
        image_bytes: bytes,
        page_number: int,
        *,
        context_hint: str | None = None,
    ) -> OCRPageResult:
        if not image_bytes:
            return OCRPageResult(
                page_number=page_number,
                text="",
                confidence=0.0,
                blocks=[],
                provider=self.name,
                is_scanned=True,
                metadata={"error": "Empty image bytes"},
            )

        return await asyncio.to_thread(_process_ocr_boxes_sync, image_bytes, page_number)

