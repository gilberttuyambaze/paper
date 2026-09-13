import logging
import re
import asyncio
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.config import settings
from dependencies.auth import get_current_user
from models.comments import Comments
from models.papers import Papers, PaperPassage
from models.solutions import Solutions
from schemas.auth import UserResponse
from services.ai.base import AIGenerationRequest, AIMessage
from services.ai.papers import build_paper_context
from services.ai.service import AIService, AIProviderFactory
from services.pdf_text import extract_pdf_text
from services.storage import StorageService
from services.passage_indexing import PassageIndexService
from services.retrieval import (
    HybridRetrievalService,
    QuestionIntent,
    classify_question_intent,
    is_question_collection_query,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/study-ai", tags=["study-ai"])

# In-memory fast cache for extracted text to prevent slow redundant network downloads
_paper_text_cache: dict[int, str] = {}

STUDY_AI_SYSTEM_PROMPT = (
    "DOCUMENT-GROUNDED ACADEMIC ASSISTANT MODE\n"
    "You help a student interact naturally with one authorised academic paper. Interpret the student's request yourself; do not require commands or a fixed task taxonomy.\n\n"
    "Strict Grounding Rules (Grounding contract):\n"
    "1. Ground all document answers directly in the retrieved excerpts provided in the context.\n"
    "2. NEVER invent, hallucinate, or fabricate exam questions, question numbers, sections, passages, quotations, or page numbers.\n"
    "3. NEVER assume the paper follows a 'typical' or 'usual' format unless established by the retrieved document text.\n"
    "4. If a requested question was not found in the paper (e.g. asking for Question 99 on a 13-question paper), state clearly: 'I could not find Question X in this examination paper.' Do NOT invent an alternative question.\n"
    "5. If a page or question is marked as unreadable or cannot be extracted from the scan, state clearly: 'Page X could not be reliably extracted from this document.'\n"
    "6. Cite each material paper claim using a supplied source label such as [Page 3 • Section II • Question 2].\n"
    "7. Clearly distinguish what the paper says, reasoning from it, and general academic knowledge. State when evidence is absent, ambiguous, omitted by budget, or low-confidence.\n"
    "8. The question index is derived extraction, not proof; verify source text before claiming an inventory or answer.\n"
    "9. Give an educational response in the shape requested: explanation, navigation, comparison, revision material, solution, table, or follow-up.\n"
    "10. Never output UI, OCR scanner, SVG, or internal retrieval artifacts."
)



class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class AIActionRequest(BaseModel):
    action: str = "ask"  # retained for backwards-compatible clients; not an intent classifier
    question: str | None = None
    message: str | None = None
    chat_history: list[ChatHistoryMessage] | None = None
    preferred_provider: str | None = None


def _keywords(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-zA-Z0-9]{3,}", value.lower())
        if word not in {"what", "with", "from", "this", "that", "about", "paper", "question", "please"}
    }


def _build_fallback_response(
    action: str,
    paper: Papers,
    comments: list[Comments],
    solutions: list[Solutions],
    question: str | None = None,
    extracted_text: str | None = None,
    sources: list[dict] | None = None,
    fallback_reason: str | None = None,
) -> dict:
    discussion_points = [comment.content.strip() for comment in comments if comment.content][:5]
    solution_points = [solution.content.strip() for solution in solutions if solution.content][:5]
    paper_chunks = [
        chunk.strip()
        for chunk in re.split(r"(?<=[.!?])\s+|\n+", extracted_text or "")
        if len(chunk.strip()) >= 25
    ][:300]

    if action == "explain":
        content = (
            f"## Study Guide: {paper.course_code} - {paper.course_name}\n\n"
            f"### 1. Paper Overview\n"
            f"- **Academic Year**: {paper.year}\n"
            f"- **Paper Type**: {paper.paper_type}\n"
            f"- **Department / College**: {paper.department} ({paper.college})\n"
            f"- **Lecturer / Examiner**: {paper.lecturer or 'Not specified'}\n"
            f"- **Description**: {paper.description or 'Standard examination paper for University of Rwanda.'}\n\n"
            f"### 2. High-Yield Revision Strategy\n"
            f"- Revisit core syllabus topics from {paper.department} before attempting timed practice.\n"
            f"- Use this paper to identify question patterns, section weightings, and likely focus areas.\n"
            f"- Practice solving problems under timed exam conditions (typically 2–3 hours).\n\n"
            f"### 3. Key Resources & Community Insights\n"
            f"- **Community Discussion**: {('; '.join(discussion_points) if discussion_points else 'No student discussion notes recorded yet.')}\n"
            f"- **Top Solution Approaches**: {('; '.join(solution_points) if solution_points else 'No verified community solutions uploaded yet.')}\n"
            f"- **Document Text Status**: {'Readable PDF passages extracted and available.' if paper_chunks else 'Scanned document or no readable text.'}\n\n"
            f"### 4. Exam Technique Checklist\n"
            f"- **Time Budgeting**: Allocate time proportionally to marks per question.\n"
            f"- **First Pass**: Tackle high-confidence questions first to secure foundation marks.\n"
            f"- **Formulas & Working**: Clearly show all intermediate steps, units, and assumptions."
        )
    elif action == "summarize":
        content = (
            f"## Study Brief: {paper.title}\n\n"
            f"### Core Information\n"
            f"- **Course**: {paper.course_code} - {paper.course_name}\n"
            f"- **Level / Department**: {paper.department}\n"
            f"- **Type & Year**: {paper.paper_type} ({paper.year})\n\n"
            f"### Key Discussion Points\n"
            f"- {('; '.join(discussion_points) if discussion_points else 'No discussion entries submitted yet.')}\n\n"
            f"### Solution Highlights\n"
            f"- {('; '.join(solution_points) if solution_points else 'No verified solutions submitted yet.')}\n\n"
            f"### Recommended Study Steps\n"
            f"1. Attempt each section of the paper independently.\n"
            f"2. Compare your intermediate working with available solutions.\n"
            f"3. Join the discussion tab to discuss challenging questions with peers."
        )
    elif action == "formulas":
        content = (
            f"## Core Formulas & Definitions: {paper.course_code}\n\n"
            f"### Important Syllabus Concepts ({paper.course_name})\n"
            f"- **Course Domain**: {paper.department}\n"
            f"- **Document Structure**: {len(paper_chunks)} readable sections identified.\n\n"
            f"### Essential Review Checklist\n"
            f"1. Key Definitions: Memorize standard terminology from {paper.course_name}.\n"
            f"2. Core Formulas: Write out and practice deriving foundational formulas.\n"
            f"3. Boundary Conditions: Review edge cases and domain constraints."
        )
    elif action == "pitfalls":
        content = (
            f"## Common Exam Pitfalls & Mistakes: {paper.course_code}\n\n"
            f"### Areas to Watch Out For\n"
            f"- **Incomplete Working**: Forgetting intermediate derivation steps or units.\n"
            f"- **Time Allocation**: Spending disproportionate time on low-mark questions.\n"
            f"- **Misreading Instructions**: Missing required section choices (e.g., 'Answer any 3 of 5').\n\n"
            f"### Best Practice Advice\n"
            f"- Read all questions during the reading time before starting.\n"
            f"- Check your answers with units and dimensional analysis."
        )
    elif action == "quiz":
        content = (
            f"## Practice Self-Assessment Quiz: {paper.course_code}\n\n"
            f"### Question 1 (Core Concepts - {paper.course_name})\n"
            f"What is the primary learning objective and competence assessed in {paper.course_name} ({paper.department})?\n"
            f"- A) Surface-level memorization without application\n"
            f"- B) Application of core theories, principles, and structured problem-solving (Correct)\n"
            f"- C) Purely historical overview of concepts\n"
            f"- D) Unstructured review without derivations\n\n"
            f"**Explanation**: Mastery of {paper.course_name} requires understanding both theoretical principles and practical application.\n\n"
            f"### Question 2 (Exam Technique)\n"
            f"When tackling multi-part questions in {paper.course_code}, what is the recommended exam strategy?\n"
            f"- A) Skip reading instructions and start immediately\n"
            f"- B) Budget time based on allocated marks and write down all intermediate steps/units (Correct)\n"
            f"- C) Only attempt the last question\n"
            f"- D) Write final answers without showing working\n\n"
            f"**Explanation**: Examiners award step marks for clear derivations, formulas stated, and proper units.\n\n"
            f"### Question 3 (Revision Strategy)\n"
            f"How should students utilize this past paper ({paper.year} {paper.paper_type}) for optimal revision?\n"
            f"- A) Read answers passively\n"
            f"- B) Solve questions under timed conditions, then cross-reference with syllabus notes and peer discussions (Correct)\n"
            f"- C) Memorize question numbers only\n"
            f"- D) Wait until the night before the exam\n\n"
            f"**Explanation**: Timed active recall and peer discussion provide the strongest retention for University of Rwanda exams."
        )
    elif is_question_collection_query(question or ""):
        inventory_blocks: list[str] = []
        current_sec = None
        pages_seen: set[int] = set()
        if sources:
            for s in sources:
                sec = s.get("section_title")
                q = s.get("question_number")
                text_content = s.get("passage", "").strip()
                page = s.get("page_number", 1)
                pages_seen.add(page)

                if sec and sec != current_sec:
                    current_sec = sec
                    inventory_blocks.append(f"\n### {sec}\n")

                if q:
                    inventory_blocks.append(f"**Question {q}**:\n{text_content}\n")
                elif text_content and not text_content.startswith(("MODULE WEIGHTING", "DATE:", "LEVEL OF STUDY")):
                    inventory_blocks.append(f"{text_content}\n")

        pages_sorted = sorted(list(pages_seen)) if pages_seen else [1]
        page_str = f"Page {pages_sorted[0]}" if len(pages_sorted) == 1 else f"Pages {pages_sorted[0]}–{pages_sorted[-1]}"
        sec_label = current_sec or "Exam Paper"

        content = (
            "\n".join(inventory_blocks).strip()
            + f"\n\n**Source:** {page_str} • {sec_label}"
            if inventory_blocks
            else "No questions indexed for this section."
        )
    elif classify_question_intent(question or "") == QuestionIntent.DIRECT_ANSWER and sources:
        top_s = sources[0]
        page = top_s.get("page_number", 1)
        sec = top_s.get("section_title") or "Exam Paper"
        q_num = top_s.get("question_number") or ""
        q_label = f" • Question {q_num}" if q_num else ""
        passage_text = top_s.get("passage", "").strip()

        content = (
            f"**Answer:** [Refer to document excerpt]\n\n"
            f"**Why:** {passage_text[:200]}...\n\n"
            f"**Source:** Page {page} • {sec}{q_label}"
        )
    elif classify_question_intent(question or "") == QuestionIntent.RESOURCE_EXPLAIN:
        source_label = f"Page {sources[0].get('page_number', 1)} • {sources[0].get('section_title', 'Exam Paper')}" if sources else f"{paper.course_code} - {paper.course_name}"
        content = (
            f"**Why this resource:** It directly covers concepts, questions, and curriculum requirements tested in {paper.course_code} ({paper.course_name}).\n\n"
            f"**Source:** {source_label}"
        )
    else:
        query_words = _keywords(question or "")
        candidate_sources = [
            ("Paper Overview", f"{paper.title}. Course: {paper.course_code} - {paper.course_name}. Department: {paper.department}. {paper.description or ''}"),
            *[("Discussion Note", point) for point in discussion_points],
            *[("Community Solution", point) for point in solution_points],
            *[("Document Excerpt", chunk) for chunk in paper_chunks],
        ]
        ranked = sorted(candidate_sources, key=lambda item: len(query_words & _keywords(item[1])), reverse=True)
        matched = [f"- **{label}**: {text}" for label, text in ranked if text and (query_words & _keywords(text))][:5]

        if matched:
            relevant_text = "### Key Excerpts Matching Your Question:\n" + "\n\n".join(matched)
        else:
            fallback_items = [
                f"- **Paper Overview**: {paper.title} ({paper.course_code} - {paper.course_name}), Year {paper.year}, {paper.paper_type}.",
                f"- **Department / College**: {paper.department} ({paper.college})",
            ]
            if paper.description:
                fallback_items.append(f"- **Description**: {paper.description}")
            if paper_chunks:
                for idx, chunk in enumerate(paper_chunks[:4], 1):
                    fallback_items.append(f"- **Document Content (Section {idx})**: {chunk}")
            elif discussion_points:
                for point in discussion_points[:2]:
                    fallback_items.append(f"- **Discussion**: {point}")
            elif solution_points:
                for point in solution_points[:2]:
                    fallback_items.append(f"- **Solution**: {point}")
            relevant_text = "### Document Summary & Available Content:\n" + "\n\n".join(fallback_items)

        content = (
            f"## Local Paper Study Guide\n\n"
            f"**Question / Topic**: {question}\n\n"
            f"{relevant_text}\n\n"
            f"### Suggested Study Advice\n"
            f"- Review the complete PDF document using the preview or download buttons above.\n"
            f"- Add questions or solutions in the discussion section to collaborate with other University of Rwanda students."
        )

    return {
        "content": content,
        "model": "local-study-guide",
        "provider": "local",
        "usage": None,
        "sources": sources or [],
        "fallback_reason": fallback_reason,
    }


async def _ping_provider(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Fast healthcheck for an individual provider."""
    if not spec.get("is_configured"):
        return {
            "name": name,
            "label": spec["label"],
            "model": spec["model"],
            "is_configured": False,
            "is_connected": False,
            "latency_ms": None,
            "status": "not_configured",
            "message": "API key not configured",
        }

    started = monotonic()
    try:
        prov = AIProviderFactory.create(name)
        test_req = AIGenerationRequest(
            messages=[AIMessage(role="user", content="Ping healthcheck")],
            max_output_tokens=5,
            temperature=0.0,
            user_id="healthcheck",
        )
        await asyncio.wait_for(prov.generate(test_req), timeout=3.5)
        elapsed_ms = round((monotonic() - started) * 1000)
        return {
            "name": name,
            "label": spec["label"],
            "model": spec["model"],
            "is_configured": True,
            "is_connected": True,
            "latency_ms": elapsed_ms,
            "status": "online",
            "message": f"Online and responding ({elapsed_ms}ms)",
        }
    except Exception as exc:
        elapsed_ms = round((monotonic() - started) * 1000)
        raw_msg = str(exc)
        is_quota = "quota" in raw_msg.lower() or "credit" in raw_msg.lower() or "429" in raw_msg
        return {
            "name": name,
            "label": spec["label"],
            "model": spec["model"],
            "is_configured": True,
            "is_connected": False,
            "latency_ms": elapsed_ms if is_quota else None,
            "status": "quota_exhausted" if is_quota else "error",
            "message": raw_msg if raw_msg else "Could not connect",
        }


@router.get("/status")
async def get_ai_status(
    _current_user: UserResponse = Depends(get_current_user),
):
    """Return live connectivity, multi-provider statuses, and diagnostic details."""
    if not settings.ai_enabled:
        return {
            "enabled": False,
            "active_provider": settings.ai_provider,
            "active_model": settings.openai_model,
            "is_connected": False,
            "latency_ms": None,
            "status": "disabled",
            "message": "AI assistant is disabled in server configuration (AI_ENABLED=false).",
            "providers": [],
        }

    all_specs = AIProviderFactory.get_all_provider_specs()
    # Ping only configured providers concurrently (max 3.5s total)
    tasks = [_ping_provider(item["name"], item) for item in all_specs]
    provider_results = await asyncio.gather(*tasks)

    # Find the fastest online provider
    online_providers = [p for p in provider_results if p["is_connected"]]
    quota_exhausted = [p for p in provider_results if p["status"] == "quota_exhausted"]

    if online_providers:
        # Sort by latency
        best = min(online_providers, key=lambda x: x["latency_ms"] or 9999)
        return {
            "enabled": True,
            "active_provider": best["name"],
            "active_model": best["model"],
            "is_connected": True,
            "latency_ms": best["latency_ms"],
            "status": "online",
            "message": f"AI provider '{best['label']}' is online and responding ({best['latency_ms']}ms).",
            "providers": provider_results,
        }
    elif quota_exhausted:
        first_q = quota_exhausted[0]
        return {
            "enabled": True,
            "active_provider": first_q["name"],
            "active_model": first_q["model"],
            "is_connected": False,
            "latency_ms": None,
            "status": "quota_exhausted",
            "message": f"Provider '{first_q['label']}' exhausted API quota (429). Local Paper Mode active.",
            "providers": provider_results,
        }
    else:
        configured_any = any(p["is_configured"] for p in provider_results)
        return {
            "enabled": True,
            "active_provider": settings.ai_provider,
            "active_model": settings.openai_model,
            "is_connected": False,
            "latency_ms": None,
            "status": "not_configured" if not configured_any else "error",
            "message": "No AI API keys configured" if not configured_any else "Could not reach any configured AI providers.",
            "providers": provider_results,
        }


def _clean_direct_answer_noise(text: str) -> str:
    """Strips unnecessary trailing generic advice, tutorial tables, or step numbers from direct exam answers."""
    noise_patterns = [
        re.compile(r"\n+##?\s*(?:Step[- ]by[- ]Step|Distractor Analysis|Generic Tips|Study Advice|Summary|Pedagogical Note).*$", re.DOTALL | re.IGNORECASE),
        re.compile(r"\n+When answering multiple[- ]choice.*$", re.DOTALL | re.IGNORECASE),
        re.compile(r"\n+Underline key(?:words| sentences).*$", re.DOTALL | re.IGNORECASE),
        re.compile(r"\n+This systematic approach.*$", re.DOTALL | re.IGNORECASE),
    ]
    cleaned = text
    for pattern in noise_patterns:
        cleaned = pattern.sub("", cleaned)
    return cleaned.strip()


@router.post("/papers/{paper_id}")
async def study_paper(
    paper_id: int,
    payload: AIActionRequest,
    _current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    comments_result = await db.execute(
        select(Comments).where(Comments.paper_id == paper_id).order_by(Comments.created_at.desc()).limit(8)
    )
    solutions_result = await db.execute(
        select(Solutions).where(Solutions.paper_id == paper_id).order_by(Solutions.upvotes.desc()).limit(5)
    )
    comments = comments_result.scalars().all()
    solutions = solutions_result.scalars().all()

    action = payload.action.lower().strip()
    student_request = (payload.message or payload.question or "").strip()
    # Legacy preset buttons are converted into ordinary user utterances at the
    # boundary. They never select a different retrieval or reasoning pipeline.
    legacy_prompts = {
        "explain": "Give me a grounded study guide for this paper.",
        "summarize": "Summarize this paper and its assessed topics.",
        "formulas": "Create revision material for formulas, definitions, and concepts in this paper.",
        "pitfalls": "Identify likely conceptual pitfalls in this paper, grounding them in its questions.",
        "quiz": "Create a practice quiz based on this paper and explain its relationship to the source.",
    }
    prompt = student_request or legacy_prompts.get(action, "Help me understand this paper.")

    # Load the whole authorised paper first. Context selection happens after a
    # complete manifest exists; retrieval is not allowed to redefine the paper.
    extracted_text = None
    result = await db.execute(select(PaperPassage).where(PaperPassage.paper_id == paper.id).order_by(PaperPassage.page_number, PaperPassage.passage_index))
    passages = result.scalars().all()
    if not passages and paper.file_key:
        try:
            indexer = PassageIndexService(db)
            await asyncio.wait_for(indexer.index_paper(paper), timeout=30.0)
            result = await db.execute(select(PaperPassage).where(PaperPassage.paper_id == paper.id).order_by(PaperPassage.page_number, PaperPassage.passage_index))
            passages = result.scalars().all()
        except Exception as exc:
            logger.info("Auto-indexing fallback on study_paper: %s", exc)

    context_tokens = max(1, min(12000, settings.ai_max_context_tokens))
    context = build_paper_context(
        paper=paper,
        comments=comments,
        solutions=solutions,
        max_tokens=context_tokens,
        passages=passages,
        extracted_text=extracted_text,
        query=prompt,
    )
    source_items = [
        {"paper_id": paper.id, "paper_title": paper.title, "page_number": p.page_number, "question_number": p.question_number, "section_title": p.section_title, "passage": p.text}
        for p in passages if p.id in context.source_ids
    ]

    # Check if any server-side AI provider is enabled and configured
    if not AIService.is_configured():
        return _build_fallback_response("question", paper, comments, solutions, prompt, extracted_text, source_items, "cloud_ai_not_configured")

    try:
        system_prompt = STUDY_AI_SYSTEM_PROMPT
        max_tokens = min(settings.ai_max_output_tokens, 4096)

        messages = [
            AIMessage(role="system", content=system_prompt),
            AIMessage(
                role="system",
                content=f"Authorized Paper Context ({paper.course_code} - {paper.course_name}):\n{context.text}",
            ),
        ]

        if payload.chat_history:
            for history_item in payload.chat_history[-8:]:
                if history_item.content and history_item.content.strip():
                    messages.append(
                        AIMessage(role=history_item.role, content=history_item.content.strip())
                    )

        messages.append(AIMessage(role="user", content=prompt))

        # Use fast multi-provider waterfall (fails over in milliseconds if preferred/primary fails)
        response = await AIService().generate_with_waterfall(
            AIGenerationRequest(
                temperature=0.2,
                max_output_tokens=max_tokens,
                user_id=str(_current_user.id),
                messages=messages,
            ),
            preferred_provider=payload.preferred_provider,
            per_provider_timeout=20.0,
        )

        final_content = response.content

        return {
            "content": final_content,
            "model": response.model,
            "provider": response.provider,
            "usage": response.usage.__dict__ if response.usage else None,
            "duration_ms": response.duration_ms,
            "sources": source_items,
        }
    except Exception as exc:
        logger.warning("Study AI request failed across providers, using fallback summary: %s", exc)
        raw_reason = str(exc) if str(exc) else getattr(exc, "code", "cloud_ai_unavailable")
        return _build_fallback_response("question", paper, comments, solutions, prompt, extracted_text, source_items, raw_reason)


@router.post("/papers/{paper_id}/reprocess")
async def reprocess_paper(
    paper_id: int,
    _current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reprocesses document extraction and re-indexes passages without data duplication."""
    paper = await db.get(Papers, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not paper.file_key:
        raise HTTPException(status_code=400, detail="Paper has no document file to reprocess")

    indexer = PassageIndexService(db)
    result = await indexer.index_paper(paper)
    return {
        "success": True,
        "paper_id": paper_id,
        "extraction_status": paper.extraction_status,
        "extraction_method": paper.extraction_method,
        "extraction_quality": paper.extraction_quality,
        "ocr_used": paper.ocr_used,
        "passages_indexed": result.get("passages", 0),
        "embedded_count": result.get("embedded", 0),
    }
