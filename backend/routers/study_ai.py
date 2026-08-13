import logging

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/study-ai", tags=["study-ai"])


class AIActionRequest(BaseModel):
    action: str


def _build_fallback_response(action: str, paper: Papers, comments: list[Comments], solutions: list[Solutions]) -> dict:
    discussion_points = [comment.content.strip() for comment in comments if comment.content][:3]
    solution_points = [solution.content.strip() for solution in solutions if solution.content][:3]

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
            "4. Exam technique\n"
            "- Practice answering in timed blocks.\n"
            "- Mark difficult questions first and come back after securing easy marks.\n"
            "- Use the paper to build a checklist of topics you still need to revise."
        )
    else:
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
            "Recommended next step\n"
            "- Review the paper question by question, then compare your answers with the strongest community notes or solutions."
        )

    return {
        "content": content,
        "model": "local-study-guide",
        "usage": None,
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
    else:
        raise HTTPException(status_code=400, detail="Unsupported AI action")

    context = build_paper_context(
        paper=paper,
        comments=comments,
        solutions=solutions,
        max_tokens=max(1, min(6000, settings.ai_max_context_tokens // 2)),
    )

    try:
        response = await AIService().analyze_paper(
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
        )
        return {"content": response.content, "model": response.model, "usage": response.usage.__dict__ if response.usage else None}
    except Exception as exc:
        logger.warning("Study AI request failed, using fallback summary: %s", exc)
        return _build_fallback_response(action, paper, comments, solutions)
