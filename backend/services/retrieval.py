"""Hybrid passage retrieval: exact question routing, context expansion, keyword matching, and semantic similarity."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.papers import PaperPassage
from services.embeddings import EmbeddingService


@dataclass(frozen=True)
class RetrievedPassage:
    passage: PaperPassage
    score: float
    keyword_score: float
    semantic_score: float | None
    is_exact_question_match: bool = False
    context_role: str = "target_question"  # "target_question" | "reading_passage" | "section_header" | "options_continuation"


from enum import Enum


class QuestionIntent(str, Enum):
    COLLECTION = "collection"
    DIRECT_ANSWER = "direct_answer"
    EXPLAIN = "explain"
    STEP_BY_STEP = "step_by_step"
    TEACH_ME = "teach_me"
    RESOURCE_EXPLAIN = "resource_explain"
    GENERAL = "general"


def _terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-zA-Z0-9]{2,}", value.lower())
        if term not in {
            "what", "is", "the", "and", "for", "with", "this", "that", "about",
            "how", "why", "solve", "calculate", "find", "explain", "step", "by"
        }
    }


def is_question_collection_query(query: str) -> bool:
    """Detects requests that ask to list, collect, or outline all questions from the paper without solving."""
    q = query.lower().strip()
    if re.search(r"\b(?:solve|answer|work\s+out|solutions?\s+for|how\s+to\s+solve|calculate)\b", q):
        return False
    patterns = [
        r"\bcollect\b.*?\bquestions?\b",
        r"\blist\b.*?\bquestions?\b",
        r"\bshow\b.*?\bquestions?\b",
        r"\ball\s+questions?\b",
        r"\bevery\s+question\b",
        r"\bwhat\s+questions\s+are\s+in\b",
        r"\bget\s+(?:all\s+)?questions?\b",
        r"\bdisplay\s+(?:all\s+)?questions?\b",
        r"\bshow\s+me\s+(?:all\s+)?(?:the\s+)?questions?\b",
        r"\bgive\s+me\s+(?:all\s+)?(?:the\s+)?questions?\b",
        r"\bquestions\s+in\s+this\s+(?:paper|section|document)\b",
        r"\bquestions\s+from\s+(?:the\s+)?(?:vocabulary|grammar|section|writing)\b",
        r"\bvocab(?:ulary)?\s+questions?\b",
        r"\bgrammar\s+questions?\b",
        r"\bhow\s+many\s+questions\b",
        r"\bquestion\s+list\b",
        r"\bquestion\s+inventory\b",
        r"\boutline\s+(?:all\s+)?questions?\b",
        r"\bextract\s+(?:all\s+)?questions?\b",
        r"\bextract\b.*?\b(?:vocabulary|grammar|section)\b",
    ]
    return any(re.search(p, q) for p in patterns)


def classify_question_intent(query: str) -> QuestionIntent:
    """Classifies user study requests into precise intent modes."""
    q = query.lower().strip()
    if is_question_collection_query(q):
        return QuestionIntent.COLLECTION

    if re.search(r"\b(?:explain\s+(?:this\s+)?resource|why\s+(?:did\s+you\s+choose|select)(?:\s+this)?\s+resource|why\s+this\s+resource|resource\s+relevance)\b", q):
        return QuestionIntent.RESOURCE_EXPLAIN

    if re.search(r"\b(?:teach\s+me|how\s+(?:should|to|do)\s+i\s+approach|exam\s+technique|strategy\s+for\s+these|how\s+to\s+answer\s+questions\s+like\s+this)\b", q):
        return QuestionIntent.TEACH_ME

    if re.search(r"\b(?:step\s*[-–—]?\s*by\s*[-–—]?\s*step|show\s+(?:all\s+)?steps|with\s+steps|detailed\s+working|derive\s+step|work\s+through\s+step)\b", q):
        return QuestionIntent.STEP_BY_STEP

    if re.search(r"\b(?:why\s+(?:is|did|does|choose|option)|explain\s+why|why\s+[a-d]\b|why\s+is\s+it\s+[a-d]|why\s+is\s+[a-d]|what\s+makes\s+[a-d]|distinguish\s+between)\b", q):
        return QuestionIntent.EXPLAIN

    # Single-question direct answer requests (solve question X, answer question Y, what is the answer to Z)
    if _extract_target_question_id(q):
        return QuestionIntent.DIRECT_ANSWER

    return QuestionIntent.GENERAL


def _extract_target_question_id(query: str) -> str | None:
    """Extracts explicit question numbers or subquestions from user query."""
    if is_question_collection_query(query):
        return None
    q = query.strip()
    # If the query is asking about an entire section (e.g. "section 2 questions"), it's not a single question
    if re.search(r"\b(?:section|part)\s*[0-9ivx]+\s*questions?\b", q, re.IGNORECASE):
        return None
    if re.search(r"\b(?:section|part)\s*[0-9ivx]+\b", q, re.IGNORECASE) and not re.search(r"\b(?:question|problem|q\.?)\s*\d+\b", q, re.IGNORECASE):
        return None

    patterns = [
        re.compile(r"\b(?:question|problem|q\.?)\s*(\d+[a-z]?(?:\s*\([a-z0-9]+\))?)(?=[\s\.,;\?!]|\b|$)", re.IGNORECASE),
        re.compile(r"\b(\d+\s*\([a-z0-9]+\))(?=[\s\.,;\?!]|\b|$)", re.IGNORECASE),
        re.compile(r"\b(?:part|subpart)\s*\(?([a-z0-9]+)\)?(?=[\s\.,;\?!]|\b|$)", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(q)
        if m:
            raw = m.group(1).strip().lower()
            return re.sub(r"\s+", "", raw)
    return None


_ROMAN_MAP = {
    "1": ["1", "i", "one"],
    "2": ["2", "ii", "il", "two"],
    "3": ["3", "iii", "ill", "three"],
    "4": ["4", "iv", "four"],
    "5": ["5", "v", "five"],
    "6": ["6", "vi", "six"],
    "i": ["1", "i", "one"],
    "ii": ["2", "ii", "il", "two"],
    "il": ["2", "ii", "il", "two"],
    "iii": ["3", "iii", "ill", "three"],
    "ill": ["3", "iii", "ill", "three"],
    "iv": ["4", "iv", "four"],
    "v": ["5", "v", "five"],
    "vi": ["6", "vi", "six"],
}


def _extract_target_section_id(query: str) -> str | None:
    """Extracts explicit section numbers, roman numerals, or named sections from query."""
    q = query.lower().strip()
    if re.search(r"\b(?:vocab|vocabulary)\b", q):
        return "vocab"
    if re.search(r"\b(?:grammar)\b", q):
        return "grammar"
    if re.search(r"\b(?:writing|essay|composition)\b", q):
        return "writing"
    if re.search(r"\breading\s*(?:comprehension)?\b", q):
        return "1"

    patterns = [
        re.compile(r"\b(?:section|part)\s*([0-9ivx]+)\b", re.IGNORECASE),
        re.compile(r"\bsection([0-9ivx]+)\b", re.IGNORECASE),
        re.compile(r"\bpart([0-9ivx]+)\b", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(q)
        if m:
            return m.group(1).strip().lower()
    return None


def _is_section_header_match(target_sec: str, sec_title: str | None, text: str | None = None) -> bool:
    if not target_sec:
        return False
    s_title = (sec_title or "").strip().lower()
    s_text = (text or "").strip().lower()[:120]

    aliases = _ROMAN_MAP.get(target_sec.lower(), [target_sec.lower()])

    if target_sec in ("vocab", "vocabulary"):
        return "vocab" in s_title or "vocab" in s_text
    if target_sec == "grammar":
        return "grammar" in s_title or "grammar" in s_text or _is_section_header_match("2", sec_title, text)
    if target_sec in ("writing", "essay"):
        return "writing" in s_title or "writing" in s_text or _is_section_header_match("3", sec_title, text)
    if target_sec in ("reading", "1", "i"):
        if "reading" in s_title or "reading" in s_text:
            return True

    for alias in aliases:
        pattern = rf"\b(?:section|part|module)\s*{re.escape(alias)}\b"
        compact_pattern = rf"\b(?:section|part|module){re.escape(alias)}\b"
        if re.search(pattern, s_title) or re.search(compact_pattern, s_title):
            return True
        if re.search(pattern, s_text) or re.search(compact_pattern, s_text):
            return True

    return False


def _section_matches(target_sec: str, sec_title: str | None) -> bool:
    return _is_section_header_match(target_sec, sec_title)


def _is_major_section_header(sec_title: str | None, text: str | None = None) -> bool:
    s_title = (sec_title or "").strip().lower()
    s_text = (text or "").strip().lower()[:120]
    pat = r"\b(?:section\s*[0-9ivx]+|section[0-9ivx]+|part\s*[a-z0-9ivx]+|module\s*[0-9ivx]+|vocabulary|writing|reading\s*comprehension)\b"
    return bool(re.search(pat, s_title) or re.search(pat, s_text))


def _get_contiguous_section_passages(target_sec: str, passages: list[PaperPassage]) -> list[PaperPassage]:
    if not target_sec or not passages:
        return []

    start_idx = -1
    for i, p in enumerate(passages):
        sec = getattr(p, "section_title", None)
        text = str(getattr(p, "text", "") or "")
        if _is_section_header_match(target_sec, sec, text):
            start_idx = i
            break

    if start_idx == -1:
        return [p for p in passages if _is_section_header_match(target_sec, getattr(p, "section_title", None), getattr(p, "text", None))]

    end_idx = len(passages)
    for i in range(start_idx + 1, len(passages)):
        p = passages[i]
        sec = getattr(p, "section_title", None)
        text = str(getattr(p, "text", "") or "")
        if _is_major_section_header(sec, text) and not _is_section_header_match(target_sec, sec, text):
            end_idx = i
            break

    return passages[start_idx:end_idx]


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
        return default
    except Exception:
        return default


class HybridRetrievalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def retrieve(
        self,
        query: str,
        *,
        paper_id: int,
        course_code: str | None = None,
        limit: int | None = None,
    ) -> list[RetrievedPassage]:
        query_terms = _terms(query)
        target_q = _extract_target_question_id(query)
        target_sec = _extract_target_section_id(query)

        try:
            result = await self.db.execute(
                select(PaperPassage)
                .where(PaperPassage.paper_id == paper_id)
                .order_by(PaperPassage.passage_index.asc())
                .limit(settings.hybrid_search_top_k)
            )
        except SQLAlchemyError:
            return []

        passages: list[PaperPassage] = result.scalars().all()
        if not passages:
            return []

        # ----------------------------------------------------
        # 1. SCOPED OR FULL QUESTION COLLECTION:
        # ----------------------------------------------------
        if is_question_collection_query(query):
            target_passages = _get_contiguous_section_passages(target_sec, passages) if target_sec else passages
            collection_passages: list[RetrievedPassage] = []
            for p in target_passages:
                p_text = str(getattr(p, "text", "") or "").strip()
                p_q = getattr(p, "question_number", None)
                p_sec = getattr(p, "section_title", None)
                p_idx = _safe_int(getattr(p, "passage_index", 0), 0)

                # Exclude university header / metadata cover items (if on page 1 before questions)
                if not target_sec and p_idx < 3 and not p_q and not p_sec:
                    continue
                if p_text.startswith(("MODULE WEIGHTING", "DATE:", "LEVEL OF STUDY")):
                    continue

                collection_passages.append(
                    RetrievedPassage(
                        passage=p,
                        score=1.0,
                        keyword_score=1.0,
                        semantic_score=None,
                        is_exact_question_match=True,
                        context_role="question_inventory",
                    )
                )

            if collection_passages:
                return collection_passages

        # ----------------------------------------------------
        # 2. TARGET SECTION ROUTING (e.g. "i need answer for section 2 questions"):
        # ----------------------------------------------------
        if target_sec and not target_q:
            contiguous = _get_contiguous_section_passages(target_sec, passages)
            if contiguous:
                return [
                    RetrievedPassage(
                        passage=p,
                        score=1.0,
                        keyword_score=1.0,
                        semantic_score=None,
                        is_exact_question_match=True,
                        context_role="target_section",
                    )
                    for p in contiguous
                ]

        # ----------------------------------------------------
        # 3. TARGET SINGLE-QUESTION ROUTING:
        # ----------------------------------------------------
        exact_matches: list[PaperPassage] = []
        if target_q:
            for p in passages:
                p_q = str(getattr(p, "question_number", "") or "").lower().replace(" ", "")
                p_text = str(getattr(p, "text", "") or "")
                if p_q and (target_q == p_q or p_q.startswith(f"{target_q}(") or p_q.startswith(f"{target_q}.")):
                    exact_matches.append(p)
                elif re.search(r"\b(?:question|q\.?|problem)\s*" + re.escape(target_q) + r"\b", p_text, re.IGNORECASE):
                    exact_matches.append(p)

            # If user explicitly asked for Question X (e.g. Question 20) and it DOES NOT exist on paper:
            # Return empty list so AI can strictly refuse rather than hallucinating random passages!
            if not exact_matches:
                return []

            if target_sec and len(exact_matches) > 1:
                sec_matches = [p for p in exact_matches if _section_matches(target_sec, getattr(p, "section_title", None))]
                if sec_matches:
                    exact_matches = sec_matches

            # ----------------------------------------------------
            # CONTEXT EXPANSION:
            # Include reading passage and options continuation for target question
            # ----------------------------------------------------
            expanded_passages: list[RetrievedPassage] = []
            seen_passage_ids: set[Any] = set()

            for match in exact_matches:
                match_id = getattr(match, "id", None)
                match_page = _safe_int(getattr(match, "page_number", 1), 1)
                match_idx = _safe_int(getattr(match, "passage_index", 0), 0)

                # Include reading text passages on earlier pages or same page that contain passage content
                for p in passages:
                    p_id = getattr(p, "id", None)
                    p_idx = _safe_int(getattr(p, "passage_index", 0), 0)
                    p_page = _safe_int(getattr(p, "page_number", 1), 1)
                    p_text = str(getattr(p, "text", "") or "")
                    p_q = getattr(p, "question_number", None)

                    if p_id not in seen_passage_ids and p_idx < match_idx:
                        if (
                            not p_q
                            and p_page in (match_page - 1, match_page - 2, match_page, 2, 3)
                            and len(p_text) > 60
                            and not p_text.strip().startswith("1. This paper contains")
                        ):
                            seen_passage_ids.add(p_id)
                            expanded_passages.append(
                                RetrievedPassage(
                                    passage=p,
                                    score=0.90,
                                    keyword_score=0.5,
                                    semantic_score=None,
                                    is_exact_question_match=False,
                                    context_role="reading_passage",
                                )
                            )

                # Add the target question itself
                if match_id not in seen_passage_ids:
                    seen_passage_ids.add(match_id)
                    expanded_passages.append(
                        RetrievedPassage(
                            passage=match,
                            score=1.0,
                            keyword_score=1.0,
                            semantic_score=None,
                            is_exact_question_match=True,
                            context_role="target_question",
                        )
                    )

                # Check if the succeeding passage is an options continuation
                for p in passages:
                    p_id = getattr(p, "id", None)
                    p_idx = _safe_int(getattr(p, "passage_index", 0), 0)
                    p_text = str(getattr(p, "text", "") or "")
                    p_q = getattr(p, "question_number", None)

                    if p_id not in seen_passage_ids and p_idx == match_idx + 1:
                        if not p_q and (
                            p_text.strip().startswith(("D.", "d)", "C.", "c)", "B.", "b)", "4.", "5.", "A.", "a)"))
                            or len(p_text) < 150
                        ):
                            seen_passage_ids.add(p_id)
                            expanded_passages.append(
                                RetrievedPassage(
                                    passage=p,
                                    score=0.85,
                                    keyword_score=0.5,
                                    semantic_score=None,
                                    is_exact_question_match=False,
                                    context_role="options_continuation",
                                )
                            )

            expanded_passages.sort(
                key=lambda item: (
                    _safe_int(getattr(item.passage, "page_number", 1), 1),
                    _safe_int(getattr(item.passage, "passage_index", 0), 0),
                )
            )
            # For exact question matches, return the complete question context without truncating away the target question
            max_expand = max(limit or settings.vector_search_top_k, len(expanded_passages))
            return expanded_passages[:min(max_expand, 12)]

        # General semantic and keyword retrieval
        query_embedding = None
        embedding_provider = next((getattr(passage, "embedding_provider", None) for passage in passages if getattr(passage, "embedding_status", None) == "ready" and getattr(passage, "embedding_provider", None)), None)
        try:
            query_embedding = await EmbeddingService().generate_embedding(query, provider=embedding_provider)
        except Exception:
            query_embedding = None

        postgres_scores: dict[int, float] = {}
        if query_embedding and self.db.bind and getattr(self.db.bind, "dialect", None) and self.db.bind.dialect.name == "postgresql":
            try:
                vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
                rows = await self.db.execute(
                    text(
                        "SELECT id, 1 - (embedding_vector <=> CAST(:vector AS vector)) AS score "
                        "FROM paper_passages WHERE paper_id = :paper_id AND embedding_provider = :embedding_provider AND embedding_vector IS NOT NULL "
                        "ORDER BY embedding_vector <=> CAST(:vector AS vector) LIMIT :limit"
                    ),
                    {"vector": vector_literal, "paper_id": paper_id, "embedding_provider": embedding_provider, "limit": settings.hybrid_search_top_k},
                )
                postgres_scores = {int(row.id): float(row.score) for row in rows}
            except Exception:
                postgres_scores = {}

        ranked: list[RetrievedPassage] = []
        for passage in passages:
            p_text = str(getattr(passage, "text", "") or "")
            text_terms = _terms(p_text)
            keyword_score = len(query_terms & text_terms) / max(1, len(query_terms)) if query_terms else 0.0

            p_course = getattr(passage, "course_code", None)
            if course_code and p_course and str(p_course).lower() == course_code.lower():
                keyword_score += 0.15

            semantic_score = None
            p_id = getattr(passage, "id", None)
            if p_id in postgres_scores:
                semantic_score = postgres_scores[p_id]
            elif query_embedding and getattr(passage, "embedding_json", None) and getattr(passage, "embedding_provider", None) == embedding_provider:
                try:
                    semantic_score = _cosine(query_embedding, json.loads(passage.embedding_json))
                except (ValueError, TypeError):
                    pass

            conf_factor = getattr(passage, "extraction_confidence", None)
            conf_val = float(conf_factor) if isinstance(conf_factor, (int, float)) else 1.0
            base_semantic = ((semantic_score + 1.0) / 2.0) if semantic_score is not None else 0.0
            combined_score = (keyword_score * 0.40 + base_semantic * 0.60) * max(0.4, conf_val)

            if keyword_score > 0 or semantic_score is not None:
                ranked.append(RetrievedPassage(passage, combined_score, keyword_score, semantic_score, False))

        return sorted(ranked, key=lambda item: item.score, reverse=True)[: limit or settings.vector_search_top_k]
