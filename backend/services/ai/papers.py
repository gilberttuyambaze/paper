"""Canonical, provider-neutral Paper Intelligence Context preparation.

This module does not classify a student's intent. It faithfully represents the
authorised paper, leaving natural-language interpretation to the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class PaperContext:
    text: str
    estimated_tokens: int
    truncated: bool
    selection_mode: str = "complete"
    source_ids: list[int] = field(default_factory=list)


def clean_ocr_artifacts(text: str) -> str:
    """Removes stray scanner footers without mutating valid exam text."""
    cleaned = re.sub(r"\b(?:CS\s*)?Cam\s*Scanner\b", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*CS\s*$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]{3,}", value.lower()))


def _source_label(p: object) -> str:
    bits = [f"Page {getattr(p, 'page_number', '?')}"]
    if getattr(p, "section_title", None):
        bits.append(str(getattr(p, "section_title")))
    if getattr(p, "question_number", None):
        bits.append(f"Question {getattr(p, 'question_number')}")
    return " • ".join(bits)


def _render_unit(p: object) -> str:
    confidence = getattr(p, "extraction_confidence", None)
    method = getattr(p, "extraction_method", None) or "unknown"
    quality = f"; confidence={float(confidence):.2f}" if isinstance(confidence, (int, float)) else ""
    return f"[SOURCE id={getattr(p, 'id', '?')}; {_source_label(p)}; method={method}{quality}]\n{clean_ocr_artifacts(str(getattr(p, 'text', '') or ''))}"


def build_question_inventory(passages: Iterable[object]) -> list[dict[str, object]]:
    """Build the ordered, source-faithful task inventory used by Study AI.

    It deliberately groups only contiguous passages with the same extracted
    section/question label.  Unnumbered instructions and assessment tasks stay
    unnumbered rather than being fabricated as questions.
    """
    items: list[dict[str, object]] = []
    for passage in passages:
        section = str(getattr(passage, "section_title", None) or "Unsectioned content")
        number = getattr(passage, "question_number", None)
        text = clean_ocr_artifacts(str(getattr(passage, "text", "") or ""))
        if not text:
            continue
        key = (section, str(number) if number is not None else None)
        if items and items[-1]["group_key"] == key:
            items[-1]["source_ids"].append(int(getattr(passage, "id", 0) or 0))
            items[-1]["page_end"] = int(getattr(passage, "page_number", 0) or 0)
            items[-1]["text"].append(text)
            continue
        items.append({
            "group_key": key,
            "section": section,
            "question_number": str(number) if number is not None else None,
            "page_start": int(getattr(passage, "page_number", 0) or 0),
            "page_end": int(getattr(passage, "page_number", 0) or 0),
            "source_ids": [int(getattr(passage, "id", 0) or 0)],
            "text": [text],
            "method": getattr(passage, "extraction_method", None) or "unknown",
            "confidence": getattr(passage, "extraction_confidence", None),
        })
    return items


def _build_manifest(paper: object, passages: list[object]) -> str:
    sections: dict[str, dict] = {}
    pages: dict[int, list[object]] = {}
    inventory = build_question_inventory(passages)
    for p in passages:
        page = int(getattr(p, "page_number", 0) or 0)
        pages.setdefault(page, []).append(p)
        section = str(getattr(p, "section_title", None) or "Unsectioned content")
        data = sections.setdefault(section, {"pages": set(), "questions": []})
        data["pages"].add(page)
        if getattr(p, "question_number", None):
            data["questions"].append(p)
    lines = [
        "=== 1. PAPER METADATA ===",
        "=== PAPER IDENTITY & EXTRACTION STATUS ===",
        f"Title: {getattr(paper, 'title', '')}",
        f"Course: {getattr(paper, 'course_code', '')} - {getattr(paper, 'course_name', '')}",
        f"Paper: {getattr(paper, 'paper_type', '')}; academic year: {getattr(paper, 'year', '')}",
        f"Extraction: status={getattr(paper, 'extraction_status', 'unknown')}; method={getattr(paper, 'extraction_method', 'unknown')}; quality={getattr(paper, 'extraction_quality', 'unknown')}; failed_pages={getattr(paper, 'failed_pages', '[]')}",
        "", "=== 2. DOCUMENT STRUCTURE & SECTIONS ===",
        "=== NAVIGATION MANIFEST (complete, ordered) ===",
    ]
    for title, data in sections.items():
        qs = [str(getattr(p, "question_number")) for p in data["questions"]]
        lines.append(f"- Section: {title} | pages: {', '.join(str(n) for n in sorted(data['pages']))} | questions detected: {', '.join(qs) or 'none / not confidently parsed'}")
    lines += ["", "=== 4. CANONICAL ASSESSMENT INVENTORY (complete, ordered) ==="]
    if inventory:
        for ordinal, item in enumerate(inventory, 1):
            label = f"Question {item['question_number']}" if item["question_number"] else "Unnumbered assessment item"
            confidence = item["confidence"]
            confidence_label = f"; confidence={float(confidence):.2f}" if isinstance(confidence, (int, float)) else ""
            excerpt = " ".join(item["text"]).replace("\n", " ")[:340]
            lines.append(
                f"- Inventory {ordinal}: {item['section']} • {label} • pages {item['page_start']}-{item['page_end']} "
                f"• sources={','.join(str(source_id) for source_id in item['source_ids'])} • method={item['method']}{confidence_label}\n"
                f"  Extracted wording: {excerpt}"
            )
    else:
        lines.append("- No assessment boundaries were confidently extracted. Inspect page units before asserting an inventory.")
    lines += ["", "=== PAGE INVENTORY ==="]
    lines.extend(f"- Page {page}: {len(units)} source units; methods: {', '.join(sorted({str(getattr(p, 'extraction_method', None) or 'unknown') for p in units}))}" for page, units in pages.items())
    return "\n".join(lines)


def _select_units(passages: list[object], query: str, budget_chars: int) -> list[object]:
    """Cost control only: keep matching units, neighbours, and every section."""
    terms = _terms(query)
    chosen: set[int] = set()
    seen_sections: set[str] = set()
    for i, p in enumerate(passages):
        section = str(getattr(p, "section_title", None) or "Unsectioned content")
        if section not in seen_sections:
            chosen.add(i)
            seen_sections.add(section)
    ranked = sorted(range(len(passages)), key=lambda i: len(terms & _terms(str(getattr(passages[i], "text", "")))), reverse=True)
    for i in ranked:
        chosen.update(range(max(0, i - 1), min(len(passages), i + 2)))
        if sum(len(_render_unit(passages[n])) for n in chosen) >= budget_chars:
            break
    selected, used = [], 0
    for i in sorted(chosen):
        size = len(_render_unit(passages[i]))
        if selected and used + size > budget_chars:
            continue
        selected.append(passages[i])
        used += size
    return selected


def build_paper_intelligence_context(
    *,
    paper: object,
    comments: list[object] | None = None,
    solutions: list[object] | None = None,
    max_tokens: int = 8000,
    extracted_text: str | None = None,
    passages: Iterable[object] | None = None,
    query: str = "",
) -> PaperContext:
    ordered = sorted((getattr(item, "passage", item) for item in (passages or [])), key=lambda p: (int(getattr(p, "page_number", 0) or 0), int(getattr(p, "passage_index", 0) or 0)))
    max_chars = max(1, max_tokens) * 4
    prefix = _build_manifest(paper, ordered) + "\n\n=== 3. STRUCTURED QUESTION & SECTION CONTENT ===\n=== SOURCE UNITS IN DOCUMENT ORDER ===\n"
    all_units = "\n\n".join(_render_unit(p) for p in ordered)
    if len(prefix) + len(all_units) <= max_chars:
        text = prefix + (all_units or clean_ocr_artifacts(extracted_text or "No readable source units are indexed."))
        return PaperContext(text=text, estimated_tokens=max(1, len(text) // 4), truncated=False, source_ids=[int(getattr(p, "id", 0) or 0) for p in ordered])
    selected = _select_units(ordered, query, max(800, max_chars - len(prefix)))
    notice = "The full paper exceeds this request budget. The inventory is authoritative where present; these are relevant ordered evidence units and local neighbours. Do not claim omitted text was inspected."
    # Put the limitation first so it cannot be cut away by the hard context
    # ceiling on exceptionally large manifests.
    text = notice + "\n\n" + prefix + "\n\n".join(_render_unit(p) for p in selected)
    clipped = text[:max_chars]
    return PaperContext(text=clipped, estimated_tokens=max(1, len(clipped) // 4), truncated=True, selection_mode="structure_preserving_selection", source_ids=[int(getattr(p, "id", 0) or 0) for p in selected])


# Backward compatibility
build_paper_context = build_paper_intelligence_context
