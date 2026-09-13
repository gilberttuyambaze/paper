"""Document structure parsing and layout reconstruction for academic exam papers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StructuredUnit:
    """A cohesive unit of academic text (Question, Section Header, Subquestion, or Content Block)."""
    text: str
    page_number: int
    unit_type: str = "question"  # "section_header" | "question" | "subquestion" | "content" | "formula" | "table" | "instruction"
    question_number: str | None = None
    subquestion_number: str | None = None
    section_title: str | None = None
    parent_question_number: str | None = None
    confidence: float = 1.0
    extraction_method: str = "native"
    sub_units: list[StructuredUnit] = field(default_factory=list)


@dataclass
class DocumentStructure:
    title: str | None
    sections: list[str]
    units: list[StructuredUnit]
    detected_questions: list[str]
    overall_confidence: float


# Regex patterns for academic sections, instructions, and question numbering
SECTION_PATTERNS = [
    re.compile(r"^(?:##?\s*)?(SECTION\s*[A-Z0-9IVX]+(?:\s*[:\-–]\s*[^\n]+)?)", re.IGNORECASE),
    re.compile(r"^(?:##?\s*)?(PART\s*[A-Z0-9IVX]+(?:\s*[:\-–]\s*[^\n]+)?)", re.IGNORECASE),
    re.compile(r"^(?:##?\s*)?(MODULE\s+[0-9IVX]+(?:\s*[:\-–]\s*[^\n]+)?)", re.IGNORECASE),
    re.compile(r"^(?:##?\s*)?(COMPULSORY\s+SECTION|ELECTIVE\s+SECTION)", re.IGNORECASE),
    re.compile(r"^(?:##?\s*)?(INSTRUCTIONS?|GENERAL\s+INSTRUCTIONS?|EXAM(?:INATION)?\s+INSTRUCTIONS?)\s*[:\-–]?\s*$", re.IGNORECASE),
    re.compile(r"^(?:##?\s*)?(VOCABULARY(?:\s*[\/\(:\-–][^\n]+)?)", re.IGNORECASE),
    re.compile(r"^(?:##?\s*)?((?:I|II|III|IV|V|VI|Il|Ill|1|2|3|4)\.\s+(?:Choose|Complete|Rewrite|Match|Fill|Write|Answer|Select|Explain|Define|Read|Identify)[^\n]+)", re.IGNORECASE),
    re.compile(r"^(?:##?\s*)?((?:I|II|III|IV|V|VI|Il|Ill)\.\s+[A-Z][^\n]+)", re.IGNORECASE),
]

QUESTION_PATTERNS = [
    re.compile(r"^(?:##?\s*)?(?:QUESTION|Problem|Q\.?)\s*(\d+[a-z]?)(?:\s*[:\-–\.\)]|\b)", re.IGNORECASE),
    re.compile(r"^(\d+)\.\s+(?=[A-Z0-9\(\[])"),
    re.compile(r"^(?:##?\s*)?(\d+)\)\s+(?=[A-Z0-9])"),
]

SUBQUESTION_PATTERNS = [
    re.compile(r"^[\(\[]?([a-z]|[A-D]|[ivxlcdm]+)[\)\]\.]\s*", re.IGNORECASE),
    re.compile(r"^[A-D][\)\.]\s+"),
    re.compile(r"^(?:Part|subpart)\s+[\(\[]?([a-z0-9]+)[\)\]\.]\s*", re.IGNORECASE),
]


class DocumentStructureParser:
    """Parses raw or OCR'd page texts into hierarchical academic units."""

    @classmethod
    def parse_page_text(
        cls,
        text: str,
        page_number: int,
        *,
        extraction_method: str = "native",
        confidence: float = 1.0,
        active_section: str | None = None,
    ) -> tuple[list[StructuredUnit], str | None]:
        """Parses a single page's text into structured academic units."""
        if not text.strip():
            return [], active_section

        lines = text.split("\n")
        units: list[StructuredUnit] = []
        current_section = active_section
        current_unit: StructuredUnit | None = None
        current_lines: list[str] = []

        def flush_current():
            nonlocal current_unit, current_lines
            if current_unit and current_lines:
                current_unit.text = "\n".join(current_lines).strip()
                if current_unit.text:
                    units.append(current_unit)
            elif current_lines:
                raw = "\n".join(current_lines).strip()
                if raw:
                    units.append(
                        StructuredUnit(
                            text=raw,
                            page_number=page_number,
                            unit_type="content",
                            section_title=current_section,
                            confidence=confidence,
                            extraction_method=extraction_method,
                        )
                    )
            current_unit = None
            current_lines = []

        is_in_instructions = (current_section and "instruction" in current_section.lower()) or False

        for line in lines:
            line_str = line.strip()
            if not line_str:
                if current_lines:
                    current_lines.append("")
                continue

            # 1. Check Section header
            matched_sec = None
            for pattern in SECTION_PATTERNS:
                m = pattern.match(line_str)
                if m:
                    # On cover page before any SECTION, do not treat numbered bullet points like '3. Write...' as sections
                    if page_number == 1 and not (current_section and "section" in current_section.lower()):
                        if re.match(r"^\d+\.\s+", line_str):
                            continue
                    matched_sec = m.group(1).strip()
                    break

            if matched_sec:
                flush_current()
                current_section = matched_sec
                is_in_instructions = "instruction" in current_section.lower()
                units.append(
                    StructuredUnit(
                        text=line_str,
                        page_number=page_number,
                        unit_type="section_header",
                        section_title=current_section,
                        confidence=confidence,
                        extraction_method=extraction_method,
                    )
                )
                continue

            # If on cover page before first exam SECTION, treat numbered items as instructions/cover text
            is_exam_section_active = current_section and ("section" in current_section.lower() or "part" in current_section.lower() or "vocabulary" in current_section.lower())
            if page_number == 1 and not is_exam_section_active:
                current_lines.append(line_str)
                continue

            # 2. Check Question start
            matched_q = None
            for pattern in QUESTION_PATTERNS:
                m = pattern.match(line_str)
                if m:
                    matched_q = m.group(1).strip()
                    break

            if matched_q:
                flush_current()
                current_unit = StructuredUnit(
                    text="",
                    page_number=page_number,
                    unit_type="question",
                    question_number=matched_q,
                    section_title=current_section,
                    confidence=confidence,
                    extraction_method=extraction_method,
                )
                current_lines.append(line_str)
                continue

            # 3. Check Subquestion start (e.g. (a), (b), (i))
            matched_sub = None
            for pattern in SUBQUESTION_PATTERNS:
                m = pattern.match(line_str)
                if m:
                    matched_sub = m.group(1).strip().lower()
                    break

            if matched_sub and current_unit and current_unit.unit_type == "question":
                current_lines.append(line_str)
                continue

            # Normal line: append to active unit or accumulator
            current_lines.append(line_str)

        flush_current()
        return units, current_section

    @classmethod
    def parse_document(
        cls,
        pages: list[tuple[int, str, str, float]],  # (page_number, text, method, confidence)
    ) -> DocumentStructure:
        """Parses a full multi-page document into hierarchical structure."""
        all_units: list[StructuredUnit] = []
        all_sections: set[str] = set()
        all_questions: list[str] = []
        active_sec: str | None = None

        for page_num, page_text, method, conf in pages:
            units, active_sec = cls.parse_page_text(
                page_text,
                page_num,
                extraction_method=method,
                confidence=conf,
                active_section=active_sec,
            )
            for unit in units:
                all_units.append(unit)
                if unit.section_title and "instruction" not in unit.section_title.lower():
                    all_sections.add(unit.section_title)
                if unit.question_number and unit.question_number not in all_questions:
                    all_questions.append(unit.question_number)

        overall_conf = (
            sum(u.confidence for u in all_units) / max(1, len(all_units))
            if all_units
            else 0.0
        )

        return DocumentStructure(
            title=None,
            sections=sorted(list(all_sections)),
            units=all_units,
            detected_questions=all_questions,
            overall_confidence=round(overall_conf, 2),
        )
