"""Grounded, deterministic contributor communications backed by the event outbox."""

from __future__ import annotations

import hashlib
import html
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from models.auth import User
from models.communications import CommunicationEvent
from models.papers import Papers
from services.communications import recipient_hash
from services.mailer import (
    _brand_footer,
    _email_html_layout,
    _public_website_url,
    send_transactional_email,
)

logger = logging.getLogger(__name__)

THEMES = {
    "KNOWLEDGE_SHARING": "Knowledge becomes more valuable when it is shared. Your contribution preserves material that may help another learner revisit a difficult topic or understand how knowledge is assessed.",
    "ACADEMIC_CURIOSITY": "Learning grows through careful reading, questioning and reflection. Shared academic material gives learners more opportunities to practise those habits.",
    "ACADEMIC_STEWARDSHIP": "Preserving academic resources is a practical form of stewardship: it helps useful material remain discoverable for future learners.",
    "COMMUNITY": "A learning community becomes stronger when its members make reliable resources easier for others to find and use.",
    "INTELLECTUAL_GROWTH": "Academic growth is built through many small acts of curiosity, discipline and reflection; shared resources can support that longer journey.",
    "WISDOM": "Education is not only about collecting answers. It also develops the judgement to ask better questions, recognise patterns and reason carefully.",
    "PERSEVERANCE": "Meaningful learning usually develops over time through steady practice and return visits to challenging ideas.",
    "ACADEMIC_DISCIPLINE": "Careful academic work benefits from reliable materials, deliberate practice and attention to the evidence behind an answer.",
    "LIFELONG_LEARNING": "The habits strengthened through academic study—curiosity, reflection and careful reasoning—remain valuable well beyond a single assessment.",
    "CRITICAL_THINKING": "Resources like this can help learners examine how questions are framed, compare approaches and practise reasoning from evidence.",
    "SERVICE_TO_LEARNERS": "Making a resource available is a practical service to other learners who may be preparing, revising or seeking clearer academic context.",
}


def _theme(event_type: str, paper: Papers, user: User) -> str:
    keys = sorted(THEMES)
    digest = hashlib.sha256(f"{event_type}:{paper.id}:{user.id}:{paper.course_code}".encode()).digest()
    return keys[digest[0] % len(keys)]


def compose_contribution_message(event_type: str, paper: Papers, user: User, contribution_count: int) -> dict[str, str]:
    """Compose from trusted metadata only; uploaded PDF text is never an input."""
    name = user.name or "there"
    resource = paper.title or "your academic paper"

    course_val = None
    if getattr(paper, "course_code", None) and getattr(paper, "course_name", None):
        course_val = f"{paper.course_code} — {paper.course_name}"
    elif getattr(paper, "course_code", None) or getattr(paper, "course_name", None):
        course_val = getattr(paper, "course_code", None) or getattr(paper, "course_name", None)

    course = f" for {course_val}" if course_val else ""
    theme = THEMES[_theme(event_type, paper, user)]
    first_line = (
        "This is your first recorded paper contribution with UR Paper Hub."
        if contribution_count <= 1
        else "Thank you for continuing to contribute academic resources to UR Paper Hub."
    )

    paper_id = getattr(paper, "id", None)
    base_url = _public_website_url()
    paper_url = f"{base_url}/paper/{paper_id}" if paper_id is not None else f"{base_url}/resources"

    details_table: list[dict[str, str]] = [
        {"label": "Document Title", "value": paper.title or "Untitled Document"}
    ]
    if course_val:
        details_table.append({"label": "Course", "value": course_val})
    if getattr(paper, "department", None):
        details_table.append({"label": "Department", "value": str(paper.department)})
    if getattr(paper, "paper_type", None):
        details_table.append({"label": "Paper Type", "value": str(paper.paper_type)})
    if getattr(paper, "year", None):
        details_table.append({"label": "Academic Year", "value": str(paper.year)})

    metadata_lines = [f"• Title: {paper.title or 'Untitled Document'}"]
    if course_val:
        metadata_lines.append(f"• Course: {course_val}")
    if getattr(paper, "department", None):
        metadata_lines.append(f"• Department: {paper.department}")
    if getattr(paper, "paper_type", None):
        metadata_lines.append(f"• Paper Type: {paper.paper_type}")
    if getattr(paper, "year", None):
        metadata_lines.append(f"• Academic Year: {paper.year}")
    metadata_text_block = "\n".join(metadata_lines)

    if event_type == "PAPER_RECEIVED":
        subject = f"Your paper has been received — {resource}"
        body_lines = [
            f"Hello {name},",
            "",
            f"Thank you for contributing {resource}{course}. {first_line}",
            "",
            "Your original document and the details you supplied have been safely received. Our document intelligence system is now continuing in the background: it may examine pages, extract text, recognise scanned content where needed, identify document structure, and prepare the paper for Study AI. Processing time depends on document complexity, and you do not need to keep the upload page open.",
            "",
            "Contribution Details:",
            metadata_text_block,
            "",
            f"View Paper: {paper_url}",
            "",
            theme,
            "",
            "We will let you know when the paper is ready for Study AI.",
            "",
            _brand_footer(),
        ]
        body = "\n".join(body_lines)

        html_paragraphs = [
            f"Thank you for contributing <strong>{html.escape(resource)}</strong>{html.escape(course)}. {html.escape(first_line)}",
            "Your original document and the details you supplied have been safely received. Our document intelligence system is now continuing in the background: it may examine pages, extract text, recognise scanned content where needed, identify document structure, and prepare the paper for Study AI. Processing time depends on document complexity, and you do not need to keep the upload page open.",
            "We will notify you by email as soon as processing completes and your paper is ready for Study AI.",
        ]

        html_content = _email_html_layout(
            title="Contribution Received",
            greeting=f"Hello {html.escape(name)},",
            badge_label="Contribution Received",
            badge_type="success",
            paragraphs=html_paragraphs,
            details_table=details_table,
            action_label="View Your Paper",
            action_url=paper_url,
            notice=theme,
            notice_type="info",
        )
    else:
        subject = f"Your paper is ready for Study AI — {resource}"
        body_lines = [
            f"Hello {name},",
            "",
            f"{resource}{course} has finished academic processing and is now ready for Study AI. The original contribution remains preserved, and you can return to the paper to explore its indexed academic content.",
            "",
            "Contribution Details:",
            metadata_text_block,
            "",
            f"Study AI Paper Link: {paper_url}",
            "",
            theme,
            "",
            "Thank you for helping make academic knowledge more useful to learners.",
            "",
            _brand_footer(),
        ]
        body = "\n".join(body_lines)

        html_paragraphs = [
            f"<strong>{html.escape(resource)}</strong>{html.escape(course)} has finished academic processing and is now ready for Study AI.",
            "The original contribution remains preserved in the repository, and you can now return to the paper to explore indexed questions, key concepts, and AI study companion tools.",
        ]

        html_content = _email_html_layout(
            title="Paper Ready for Study AI",
            greeting=f"Hello {html.escape(name)},",
            badge_label="Study AI Ready",
            badge_type="success",
            paragraphs=html_paragraphs,
            details_table=details_table,
            action_label="Explore with Study AI",
            action_url=paper_url,
            notice=theme,
            notice_type="success",
        )

    return {"subject": subject, "text": body, "html": html_content}


async def record_contribution_event(db, *, event_type: str, paper: Papers, user_id: str) -> CommunicationEvent | None:
    user = await db.get(User, user_id)
    if not user or not user.email:
        logger.warning("COMMUNICATION_EVENT_NOT_CREATED paper_id=%s event_type=%s reason=missing_recipient", paper.id, event_type)
        return None
    existing = (await db.execute(select(CommunicationEvent).where(CommunicationEvent.event_type == event_type, CommunicationEvent.paper_id == paper.id))).scalar_one_or_none()
    if existing:
        logger.info("COMMUNICATION_EVENT_EXISTS event_id=%s paper_id=%s event_type=%s", existing.id, paper.id, event_type)
        return existing
    event = CommunicationEvent(
        event_type=event_type, user_id=str(user.id), paper_id=paper.id,
        recipient_hash=recipient_hash(user.email), status="pending",
        payload_json=json.dumps({"paper_id": paper.id}),
    )
    db.add(event)
    logger.info("COMMUNICATION_EVENT_CREATED event_id=pending paper_id=%s event_type=%s status=pending", paper.id, event_type)
    return event


async def deliver_pending_contribution_events(db, *, limit: int = 20) -> int:
    now = datetime.now(timezone.utc)
    # A worker restart must not strand an event in its delivery lease forever.
    await db.execute(update(CommunicationEvent).where(
        CommunicationEvent.event_type.in_(["PAPER_RECEIVED", "PAPER_PROCESSING_COMPLETED"]),
        CommunicationEvent.status == "sending",
        CommunicationEvent.delivery_started_at.is_not(None),
        CommunicationEvent.delivery_started_at < now - timedelta(minutes=10),
    ).values(status="pending", error_category="delivery_lease_recovered"))
    await db.commit()
    events = (await db.execute(select(CommunicationEvent).where(
        CommunicationEvent.event_type.in_(["PAPER_RECEIVED", "PAPER_PROCESSING_COMPLETED"]),
        CommunicationEvent.status.in_(["pending", "failed"]),
        CommunicationEvent.retry_count < 3,
    ).order_by(CommunicationEvent.created_at).limit(limit))).scalars().all()
    delivered = 0
    for event in events:
        # Conditional lease acquisition prevents duplicate sends from concurrent
        # outbox workers. A stale lease is recovered above after ten minutes.
        claim = await db.execute(update(CommunicationEvent).where(
            CommunicationEvent.id == event.id,
            CommunicationEvent.status.in_(["pending", "failed"]),
            CommunicationEvent.retry_count < 3,
        ).values(status="sending", retry_count=(event.retry_count or 0) + 1, delivery_started_at=now))
        if claim.rowcount != 1:
            logger.info("COMMUNICATION_EVENT_CLAIM_SKIPPED event_id=%s reason=owned_by_another_worker", event.id)
            continue
        await db.commit()
        await db.refresh(event)
        logger.info("COMMUNICATION_EVENT_CLAIMED event_id=%s paper_id=%s event_type=%s attempt=%s", event.id, event.paper_id, event.event_type, event.retry_count)
        paper = await db.get(Papers, event.paper_id)
        user = await db.get(User, event.user_id) if event.user_id else None
        if not paper or not user or not user.email:
            event.status, event.error_category = "failed", "missing_recipient_or_paper"
            logger.warning("COMMUNICATION_EVENT_PERMANENT_FAILURE event_id=%s paper_id=%s reason=missing_recipient_or_paper", event.id, event.paper_id)
            continue
        count = (await db.execute(select(CommunicationEvent).where(CommunicationEvent.user_id == user.id, CommunicationEvent.event_type == "PAPER_RECEIVED"))).scalars().all()
        msg = compose_contribution_message(event.event_type, paper, user, len(count))
        try:
            logger.info("EMAIL_SEND_START event_id=%s paper_id=%s event_type=%s attempt=%s", event.id, event.paper_id, event.event_type, event.retry_count)
            sent = await send_transactional_email(user.email, msg["subject"], msg["text"], msg["html"])
            event.status = "sent" if sent else "failed"
            event.error_category = None if sent else "provider_failure"
            event.sent_at = datetime.now(timezone.utc) if sent else None
            delivered += int(bool(sent))
            logger.info("EMAIL_SEND_%s event_id=%s paper_id=%s provider=brevo attempt=%s", "SUCCESS" if sent else "FAILED", event.id, event.paper_id, event.retry_count)
        except Exception as exc:
            event.status, event.error_category = "failed", type(exc).__name__[:64]
            logger.exception("EMAIL_SEND_FAILED event_id=%s paper_id=%s error_type=%s", event.id, event.paper_id, type(exc).__name__)
    await db.commit()
    return delivered
