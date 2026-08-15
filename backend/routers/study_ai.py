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
from services.ai.service import AIService
from services.pdf_text import extract_pdf_text
from services.storage import StorageService
from services.passage_indexing import PassageIndexService
from services.retrieval import HybridRetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/study-ai", tags=["study-ai"])


class AIActionRequest(BaseModel):
    action: str
    question: str | None = None


def _keywords(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-zA-Z0-9]{3,}", value.lower()) if word not in {"what", "with", "from", "this", "that", "about", "paper", "question", "please"}}


def _build_fallback_response(action: str, paper: Papers, comments: list[Comments], solutions: list[Solutions], question: str | None = None, extracted_text: str | None = None, sources: list[dict] | None = None, fallback_reason: str | None = None) -> dict:
    discussion_points = [comment.content.strip() for comment in comments if comment.content][:3]
    solution_points = [solution.content.strip() for solution in solutions if solution.content][:3]
    paper_chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+|\n+", extracted_text or "") if len(chunk.strip()) >= 25][:300]

    if action == "explain":
        content = (
            f"Study guide for {paper.course_code} - {paper.course_name}\n\n"
            f"1. Start with the paper structure\n"
            f"- Paper type: {paper.paper_type}\n"
            f"- Year: {paper.year}\n"
            f"- Lecturer: {paper.lecturer or 'Not specified'}\n\n"
            "2. Revision strategy\n"
            f"- Revisit core topics from {paper.department} before attempting timed practice.\n"
            f"- Use this paper to identify question patterns and likely focus areas.\n"
            f"- Compare your answers with any available solution or class discussion.\n\n"
            "3. What to focus on\n"
            f"- Course description clue: {paper.description or 'Review the major topics normally covered in this course.'}\n"
            f"- Community discussion highlights: {('; '.join(discussion_points) if discussion_points else 'No discussion notes yet.')}\n"
            f"- Strong solution ideas: {('; '.join(solution_points) if solution_points else 'No top solutions yet.')}\n\n"
            f"- PDF text available: {'Yes — use the question-specific assistant below for exact passages.' if paper_chunks else 'No readable PDF text was available.'}\n\n"
            "4. Exam technique\n"
            "- Practice answering in timed blocks.\n"
            "- Mark difficult questions first and come back after securing easy marks.\n"
            "- Use the paper to build a checklist of topics you still need to revise."
        )
    elif action == "summarize":
        content = (
            f"Study summary for {paper.title}\n\n"
            "Main takeaways\n"
            f"- Course: {paper.course_code} - {paper.course_name}\n"
            f"- Department: {paper.department}\n"
            f"- Paper type: {paper.paper_type}\n\n"
            "Discussion summary\n"
            f"- {('; '.join(discussion_points) if discussion_points else 'No discussion has been added yet.')}\n\n"
            "Solution summary\n"
            f"- {('; '.join(solution_points) if solution_points else 'No solutions have been submitted yet.')}\n\n"
            f"- Readable PDF text: {'Available for question matching.' if paper_chunks else 'Not available for this document.'}\n\n"
            "Recommended next step\n"
            "- Review the paper question by question, then compare your answers with the strongest community notes or solutions."
        )
    else:
        query_words = _keywords(question or "")
        candidate_sources = [
            ("Paper details", f"{paper.title}. {paper.course_code} {paper.course_name}. {paper.description or ''}"),
            *[("Discussion", point) for point in discussion_points],
            *[("Community solution", point) for point in solution_points],
            *[("PDF", chunk) for chunk in paper_chunks],
        ]
        ranked = sorted(candidate_sources, key=lambda item: len(query_words & _keywords(item[1])), reverse=True)
        relevant = [f"- {label}: {text}" for label, text in ranked if text and (not query_words or query_words & _keywords(text))][:4]
        content = (
            f"Local paper-context answer\n\nQuestion: {question}\n\n"
            + ("Relevant information available for this paper:\n" + "\n".join(relevant) if relevant else "I could not find a direct answer in this paper's saved details, discussion, or solutions.")
            + "\n\nNext step\n- Check the original PDF and add a discussion note or solution if the answer is not yet available."
        )

    return {
        "content": content,
        "model": "local-study-guide",
        "usage": None,
        "sources": sources or [],
        "fallback_reason": fallback_reason,
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
            "Explain how a student should approach this paper at the University of Rwanda. "
            "Break the answer into revision strategy, likely focus areas, and exam techniques."
        )
    elif action == "summarize":
        prompt = (
            "Summarize the paper discussion and solutions into a concise study brief with main takeaways."
        )
    elif action == "question" and payload.question and payload.question.strip():
        prompt = f"Answer this student question using only the supplied paper context: {payload.question.strip()}"
    else:
        raise HTTPException(status_code=400, detail="Unsupported AI action")

    retrieval_query = payload.question.strip() if action == "question" and payload.question else f"{paper.course_code} {paper.course_name} {action}"
    retrieval = HybridRetrievalService(db)
    retrieved = await retrieval.retrieve(retrieval_query, paper_id=paper.id, course_code=paper.course_code, limit=settings.rag_context_limit)
    if not retrieved and paper.file_key:
        # Backfill legacy papers on first use, then reuse their stored passages.
        try:
            await asyncio.wait_for(PassageIndexService(db).index_paper(paper), timeout=5)
            retrieved = await retrieval.retrieve(retrieval_query, paper_id=paper.id, course_code=paper.course_code, limit=settings.rag_context_limit)
        except Exception as exc:
            logger.info("Could not index legacy paper_id=%s: %s", paper_id, exc)
    source_items = [{"paper_id": paper.id, "paper_title": paper.title, "page_number": item.passage.page_number, "passage": item.passage.text, "score": round(item.score, 3)} for item in retrieved]
    extracted_text = "\n\n".join(f"[Page {item.passage.page_number}] {item.passage.text}" for item in retrieved)

    context = build_paper_context(
        paper=paper,
        comments=comments,
        solutions=solutions,
        max_tokens=max(1, min(6000, settings.ai_max_context_tokens // 2)),
        extracted_text=extracted_text,
    )

    # No client API key is ever requested or accepted. An administrator may opt
    # into a server-side provider; otherwise the local context responder remains usable.
    if not settings.ai_enabled or not settings.openai_api_key:
        return _build_fallback_response(action, paper, comments, solutions, payload.question, extracted_text, source_items, "cloud_ai_not_configured")

    try:
        response = await asyncio.wait_for(
            AIService().analyze_paper(
                AIGenerationRequest(
                    temperature=0.4,
                    max_output_tokens=650,
                    user_id=str(_current_user.id),
                    messages=[
                        AIMessage(
                            role="system",
                            content=(
                                "You are a helpful academic study assistant for University of Rwanda students. "
                                "Give structured, practical answers with headings, bullet points, and concrete revision advice. "
                                "Use only the supplied context; state when it does not contain enough evidence."
                            ),
                        ),
                        AIMessage(role="user", content=f"{prompt}\n\nAuthorized context:\n{context.text}"),
                    ],
                )
            ),
            timeout=min(12, settings.ai_timeout_seconds),
        )
        return {"content": response.content, "model": response.model, "usage": response.usage.__dict__ if response.usage else None, "sources": source_items}
    except Exception as exc:
        logger.warning("Study AI request failed, using fallback summary: %s", exc)
        return _build_fallback_response(action, paper, comments, solutions, payload.question, extracted_text, source_items, getattr(exc, "code", "cloud_ai_unavailable"))
