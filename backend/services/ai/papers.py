"""Bounded, provider-neutral academic-paper context preparation.

The current data model stores paper metadata and file pointers, not extracted PDF
text.  This module therefore uses available authorized metadata/discussion/solution
text and is ready to accept extracted text when a storage-safe extractor is added.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaperContext:
    text: str
    estimated_tokens: int
    truncated: bool


def _clip(value: str, remaining_chars: int) -> tuple[str, bool]:
    if len(value) <= remaining_chars:
        return value, False
    return value[: max(0, remaining_chars)].rstrip() + "…", True


def build_paper_context(
    *,
    paper: object,
    comments: list[object],
    solutions: list[object],
    max_tokens: int,
    extracted_text: str | None = None,
) -> PaperContext:
    """Create bounded context without blindly transmitting an entire PDF."""
    max_chars = max(1, max_tokens) * 4
    fields = [
        ("Paper title", getattr(paper, "title", "")),
        ("Course", f"{getattr(paper, 'course_code', '')} - {getattr(paper, 'course_name', '')}"),
        ("College", getattr(paper, "college", "")),
        ("Department", getattr(paper, "department", "")),
        ("Year", str(getattr(paper, "year", ""))),
        ("Paper type", getattr(paper, "paper_type", "")),
        ("Lecturer", getattr(paper, "lecturer", "") or "Unknown"),
        ("Description", getattr(paper, "description", "") or "None"),
    ]
    parts = [f"{name}: {value}" for name, value in fields]
    if extracted_text:
        parts.append("Extracted paper text:\n" + extracted_text)
    if comments:
        parts.append("Recent discussion:\n" + "\n".join(f"- {getattr(item, 'content', '')}" for item in comments if getattr(item, "content", None)))
    if solutions:
        parts.append("Top solutions:\n" + "\n".join(f"- {getattr(item, 'content', '')}" for item in solutions if getattr(item, "content", None)))

    assembled = "\n\n".join(parts)
    clipped, truncated = _clip(assembled, max_chars)
    return PaperContext(text=clipped, estimated_tokens=max(1, len(clipped) // 4), truncated=truncated)
