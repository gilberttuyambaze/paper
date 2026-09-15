"""Small, deterministic presentation guard for Study AI responses.

This is intentionally conservative: it removes only known transport/UI noise
and closes syntax that would otherwise break Markdown rendering.  It never
rewrites exam wording, maths, or claims drawn from the paper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_UI_ARTIFACT_LINE = re.compile(r"^\s*(?:svg(?:copy|ai study guide|optional ideas)?|copy|study ai)\s*$", re.IGNORECASE)
_SOURCES_HEADING = re.compile(r"^\s*(?:#{1,6}\s*)?sources?\s*:??\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ResponseQuality:
    empty: bool
    unclosed_code_fence: bool
    unbalanced_latex: bool
    duplicate_source_heading: bool
    removed_ui_artifacts: int


def normalize_study_response(content: str) -> tuple[str, ResponseQuality]:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    removed = 0
    source_headings = 0
    for line in lines:
        if _UI_ARTIFACT_LINE.match(line):
            removed += 1
            continue
        if _SOURCES_HEADING.match(line):
            source_headings += 1
            if source_headings > 1:
                continue
        output.append(line.rstrip())
    normalized = "\n".join(output).strip()
    fence_count = len(re.findall(r"^```", normalized, flags=re.MULTILINE))
    unclosed_fence = bool(fence_count % 2)
    if unclosed_fence:
        normalized += "\n```"
    # Only detect delimiters the system prompt asks models to use. Dollar math
    # is rendered in the browser and must remain untouched here.
    unbalanced_latex = normalized.count(r"\(") != normalized.count(r"\)") or normalized.count(r"\[") != normalized.count(r"\]")
    return normalized, ResponseQuality(
        empty=not bool(normalized),
        unclosed_code_fence=unclosed_fence,
        unbalanced_latex=unbalanced_latex,
        duplicate_source_heading=source_headings > 1,
        removed_ui_artifacts=removed,
    )
