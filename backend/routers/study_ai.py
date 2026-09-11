import logging
import re
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.config import settings
from dependencies.auth import get_current_user
from models.comments import Comments
from models.papers import Papers
from models.solutions import Solutions
from schemas.auth import UserResponse
from services.ai.base import AIGenerationRequest, AIMessage
from services.ai.papers import build_paper_context
from services.ai.service import AIService, AIProviderFactory
from services.pdf_text import extract_pdf_text
from services.storage import StorageService
from services.passage_indexing import PassageIndexService
from services.retrieval import HybridRetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/study-ai", tags=["study-ai"])


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class AIActionRequest(BaseModel):
    action: str  # explain, summarize, question, quiz, formulas, pitfalls
    question: str | None = None
    chat_history: list[ChatHistoryMessage] | None = None


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
        "usage": None,
        "sources": sources or [],
        "fallback_reason": fallback_reason,
    }


@router.get("/status")
async def get_ai_status(
    _current_user: UserResponse = Depends(get_current_user),
):
    """Return live connectivity, provider name, and diagnostic status."""
    if not settings.ai_enabled:
        return {
            "enabled": False,
            "provider": settings.ai_provider,
            "model": settings.openai_model,
            "is_connected": False,
            "latency_ms": None,
            "status": "disabled",
            "message": "AI assistant is disabled in server configuration (AI_ENABLED=false).",
        }

    provider_name, api_key, base_url, model = AIProviderFactory.detect_provider()
    if not AIProviderFactory.is_configured():
        return {
            "enabled": True,
            "provider": provider_name,
            "model": model,
            "is_connected": False,
            "latency_ms": None,
            "status": "not_configured",
            "message": f"API key is not configured for provider '{provider_name}'.",
        }

    started = asyncio.get_event_loop().time()
    try:
        service = AIService()
        test_request = AIGenerationRequest(
            messages=[AIMessage(role="user", content="Ping healthcheck")],
            max_output_tokens=5,
            temperature=0.0,
            user_id="status-check",
        )
        response = await asyncio.wait_for(service.generate(test_request), timeout=8.0)
        elapsed_ms = round((asyncio.get_event_loop().time() - started) * 1000)
        return {
            "enabled": True,
            "provider": response.provider or provider_name,
            "model": response.model or model,
            "is_connected": True,
            "latency_ms": elapsed_ms,
            "status": "online",
            "message": f"AI provider '{response.provider or provider_name}' is online and responding ({elapsed_ms}ms).",
        }
    except Exception as exc:
        raw_msg = str(exc)
        is_quota = "quota" in raw_msg.lower() or "credit" in raw_msg.lower() or "429" in raw_msg
        return {
            "enabled": True,
            "provider": provider_name,
            "model": model,
            "is_connected": False,
            "latency_ms": None,
            "status": "quota_exhausted" if is_quota else "error",
            "message": raw_msg if raw_msg else "Could not connect to AI provider.",
        }


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
    if action == "explain":
        prompt = (
            f"Please provide a comprehensive study breakdown and revision guide for this University of Rwanda exam paper:\n"
            f"Course: {paper.course_code} - {paper.course_name} ({paper.year}, {paper.paper_type})\n"
            f"Department: {paper.department} | College: {paper.college}\n\n"
            "Structure your response with:\n"
            "## 1. Exam Overview & Core Syllabus Areas\n"
            "- Key topics, themes, and competencies assessed in this paper.\n\n"
            "## 2. Topic & Question Breakdown\n"
            "- Analysis of question types, complexity, and key concepts tested.\n\n"
            "## 3. High-Yield Revision Strategy\n"
            "- Essential definitions, formulas, theories, or algorithms students must master.\n\n"
            "## 4. Common Exam Pitfalls & Technique\n"
            "- Frequent student errors to avoid and best-practice exam time management."
        )
    elif action == "summarize":
        prompt = (
            f"Please generate a comprehensive study brief and summary for this paper:\n"
            f"Course: {paper.course_code} - {paper.course_name} ({paper.year}, {paper.paper_type})\n\n"
            "Structure your response with:\n"
            "## 1. Paper Summary & Key Themes\n"
            "- Summary of core topics covered in this examination and difficulty level.\n\n"
            "## 2. Key Concepts & Formulas Tested\n"
            "- Primary definitions, formulas, and principles tested.\n\n"
            "## 3. Community Solutions & Discussion Synthesis\n"
            "- Summary of key solution insights, alternative approaches, and discussion highlights.\n\n"
            "## 4. Recommended Action Checklist\n"
            "- 3-5 concrete study action items for students preparing for this subject."
        )
    elif action == "formulas":
        prompt = (
            f"Please compile a complete reference sheet of all essential formulas, mathematical equations, definitions, and theorems tested or required for this exam:\n"
            f"Course: {paper.course_code} - {paper.course_name} ({paper.year}, {paper.paper_type})\n\n"
            "Include LaTeX formatting for all formulas, state variable definitions, and describe when to use each formula."
        )
    elif action == "pitfalls":
        prompt = (
            f"Please analyze the most common student mistakes, grading pitfalls, and tricky edge cases for this exam:\n"
            f"Course: {paper.course_code} - {paper.course_name} ({paper.year}, {paper.paper_type})\n\n"
            "Highlight specific conceptual traps, computational mistakes, and time-management risks."
        )
    elif action == "quiz":
        prompt = (
            f"Generate a 3-question practice quiz with step-by-step solutions based on the content of this exam paper:\n"
            f"Course: {paper.course_code} - {paper.course_name} ({paper.year}, {paper.paper_type})\n\n"
            "Format each question clearly, provide multiple choice options (A, B, C, D), and include a detailed explanation and answer key for each."
        )
    elif action == "question" and payload.question and payload.question.strip():
        prompt = (
            f"Student Question: {payload.question.strip()}\n\n"
            f"Course: {paper.course_code} - {paper.course_name} ({paper.year}, {paper.paper_type})\n\n"
            "Please provide a thorough, step-by-step pedagogical answer to the student's question based on the exam paper context, including detailed explanations, mathematical formulas (if applicable), derivations, and practical examples."
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported AI action")

    retrieval_query = payload.question.strip() if action == "question" and payload.question else f"{paper.course_code} {paper.course_name} {action}"
    retrieval = HybridRetrievalService(db)
    retrieved = await retrieval.retrieve(retrieval_query, paper_id=paper.id, course_code=paper.course_code, limit=settings.rag_context_limit)
    if not retrieved and paper.file_key:
        # Backfill legacy papers on first use, then reuse their stored passages.
        try:
            await asyncio.wait_for(PassageIndexService(db).index_paper(paper), timeout=8)
            retrieved = await retrieval.retrieve(retrieval_query, paper_id=paper.id, course_code=paper.course_code, limit=settings.rag_context_limit)
        except Exception as exc:
            logger.info("Could not index legacy paper_id=%s: %s", paper_id, exc)

    source_items = [{"paper_id": paper.id, "paper_title": paper.title, "page_number": item.passage.page_number, "passage": item.passage.text, "score": round(item.score, 3)} for item in retrieved]
    extracted_text = "\n\n".join(f"[Page {item.passage.page_number}] {item.passage.text}" for item in retrieved)

    # Robust fallback: if RAG passages are not yet ready or empty, extract text directly from PDF
    if not extracted_text and paper.file_key:
        try:
            pdf_bytes = await StorageService().download_file("papers", paper.file_key)
            direct_text = extract_pdf_text(pdf_bytes, max_pages=15, max_chars=32_000)
            if direct_text:
                extracted_text = direct_text
                if not source_items:
                    source_items = [{"paper_id": paper.id, "paper_title": paper.title, "page_number": 1, "passage": direct_text[:300] + "...", "score": 1.0}]
        except Exception as exc:
            logger.warning("Could not extract direct PDF text for paper_id=%s: %s", paper_id, exc)

    context = build_paper_context(
        paper=paper,
        comments=comments,
        solutions=solutions,
        max_tokens=max(1, min(6000, settings.ai_max_context_tokens // 2)),
        extracted_text=extracted_text,
    )

    # Check if server-side AI provider is enabled and configured
    if not AIService.is_configured():
        return _build_fallback_response(action, paper, comments, solutions, payload.question, extracted_text, source_items, "cloud_ai_not_configured")

    try:
        system_prompt = (
            "You are an expert Academic Study Assistant and Tutor specialized in higher education at the University of Rwanda.\n"
            "Your objective is to provide comprehensive, highly educational, accurate, and structured study guidance to students.\n\n"
            "Guidelines:\n"
            "1. Structure your answers clearly using Markdown headers (##, ###), bullet points, and bold text for key concepts.\n"
            "2. For problem-solving or questions: Provide step-by-step methodologies, clear explanations of principles, relevant mathematical formulas (in LaTeX or standard notation), and final answers.\n"
            "3. For exam preparation: Highlight core syllabus competencies, frequent exam patterns, common student pitfalls, and revision tips.\n"
            "4. Base your explanations primarily on the provided paper context, course details, questions, and discussion.\n"
            "5. If certain parts of a question are missing from the scanned text, state reasonable academic assumptions and proceed with complete, sound educational guidance.\n"
            "6. Maintain an encouraging, scholarly, and professional academic tone."
        )

        timeout_sec = max(25.0, float(settings.ai_timeout_seconds))
        max_tokens = min(settings.ai_max_output_tokens, 2048)

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

        response = await asyncio.wait_for(
            AIService().analyze_paper(
                AIGenerationRequest(
                    temperature=0.4,
                    max_output_tokens=max_tokens,
                    user_id=str(_current_user.id),
                    messages=messages,
                )
            ),
            timeout=timeout_sec,
        )
        return {
            "content": response.content,
            "model": response.model,
            "usage": response.usage.__dict__ if response.usage else None,
            "sources": source_items,
        }
    except Exception as exc:
        logger.warning("Study AI request failed, using fallback summary: %s", exc)
        raw_reason = str(exc) if str(exc) else getattr(exc, "code", "cloud_ai_unavailable")
        return _build_fallback_response(action, paper, comments, solutions, payload.question, extracted_text, source_items, raw_reason)
