"""Controlled discovery for programmes absent from the verified taxonomy."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.academic_programme_submissions import AcademicProgrammeAlias, AcademicProgrammeSubmission
from services.academic_taxonomy import NODES

NOISE = {"and", "of", "the", "in", "for", "bsc", "msc", "phd", "bachelor", "master", "science", "degree"}
PREFIX = re.compile(r"\b(b\.?\s?sc\.?|m\.?\s?sc\.?|ph\.?\s?d\.?|bachelor of science|master of science)\b", re.I)

def normalize_programme_name(value: str) -> tuple[str, str]:
    raw = unicodedata.normalize("NFKC", value).strip()
    if not raw or len(raw) > 180: raise ValueError("Programme name must be between 1 and 180 characters")
    if "<" in raw or ">" in raw: raise ValueError("Programme name cannot contain markup")
    cleaned = PREFIX.sub(" ", raw.lower().replace("&", " and "))
    cleaned = re.sub(r"[^\w\s]", " ", cleaned, flags=re.UNICODE)
    tokens = [token for token in cleaned.split() if token not in NOISE]
    if not tokens or len(" ".join(tokens)) < 3: raise ValueError("Enter a meaningful programme name")
    normalized = " ".join(tokens)
    return normalized, " ".join(sorted(set(tokens)))

def _similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = set(left.split()), set(right.split())
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens | right_tokens else 0
    edit = SequenceMatcher(None, left, right).ratio()
    return (overlap * 0.6) + (edit * 0.4)

def _context_score(candidate: dict, campus_id: str, college_id: str, school_id: str) -> float:
    return (0.15 if candidate.get("school_id") == school_id else 0) + (0.10 if candidate.get("college_id") == college_id else 0) + (0.05 if candidate.get("campus_id") == campus_id else 0)

def confidence_band(score: int) -> Optional[str]:
    # Map numeric score to human-facing band label
    if score >= 90:
        return "strong"
    if score >= 80:
        return "likely"
    if score >= 70:
        return "possible"
    return None

async def find_programme_matches(db: AsyncSession, *, institution_id: str, campus_id: str, college_id: str, school_id: str, raw_name: str) -> list[dict]:
    normalized, _tokens = normalize_programme_name(raw_name)
    candidates: list[dict] = []
    # Verified taxonomy programmes are always candidates, but their context remains part of the score.
    for node in NODES.values():
        if "-programme-" not in node.id: continue
        school = NODES.get(node.parent_id or ""); college = NODES.get(school.parent_id or "") if school else None; campus = NODES.get(college.parent_id or "") if college else None
        candidates.append({"kind": "official", "programme_id": node.id, "programme_name": node.name, "normalized": normalize_programme_name(node.name)[0], "campus_id": campus.id if campus else None, "college_id": college.id if college else None, "school_id": school.id if school else None, "occurrences": 0})
    rows = (await db.execute(select(AcademicProgrammeSubmission).where(AcademicProgrammeSubmission.institution_id == institution_id, AcademicProgrammeSubmission.status.notin_(["rejected", "merged"]), AcademicProgrammeSubmission.school_id == school_id))).scalars().all()
    for row in rows:
        candidates.append({"kind": "submission", "submission_id": str(row.id), "name": row.raw_programme_name, "normalized": row.normalized_programme_name, "campus_id": row.campus_id, "college_id": row.college_id, "school_id": row.school_id, "occurrences": 1})
    aliases = (await db.execute(select(AcademicProgrammeAlias))).scalars().all()
    for alias in aliases:
        programme = NODES.get(alias.programme_id)
        if not programme:
            continue
        school = NODES.get(programme.parent_id or "")
        college = NODES.get(school.parent_id or "") if school else None
        campus = NODES.get(college.parent_id or "") if college else None
        candidates.append({
            "kind": "alias",
            "programme_id": programme.id,
            "programme_name": programme.name,
            "normalized": alias.normalized_alias,
            "campus_id": campus.id if campus else None,
            "college_id": college.id if college else None,
            "school_id": school.id if school else None,
            "occurrences": 0,
            "alias": alias.alias,
        })
    ranked = []
    seen = set()
    for candidate in candidates:
        identity_key = candidate.get("programme_id") or candidate.get("submission_id") or candidate.get("alias") or candidate.get("name")
        identity = (candidate.get("kind"), identity_key)
        if identity in seen:
            continue
        seen.add(identity)
        similarity = _similarity(normalized, candidate["normalized"])
        score = round(100 * ((0.70 * similarity) + _context_score(candidate, campus_id, college_id, school_id)))
        band = confidence_band(score)
        # Log scoring details for debugging and diagnostics
        try:
            identity_key = identity_key  # keep identity in scope if available
        except Exception:
            identity_key = candidate.get("programme_id") or candidate.get("submission_id") or candidate.get("alias") or candidate.get("name")
        logger.debug(
            "programme_candidate score debug: id=%s kind=%s name=%s similarity=%.4f score=%d band=%s campus=%s college=%s school=%s",
            identity_key,
            candidate.get("kind"),
            candidate.get("programme_name") or candidate.get("name"),
            similarity,
            score,
            band,
            candidate.get("campus_id"),
            candidate.get("college_id"),
            candidate.get("school_id"),
        )

        # Map candidate info into canonical recommendation structure. Include weak matches
        rec = {
            "programme_id": candidate.get("programme_id"),
            "programme_name": candidate.get("programme_name") or candidate.get("name"),
            "submission_id": candidate.get("submission_id"),
            "score": score,
            "match_level": band or "weak",
            "source": candidate.get("kind"),
            "matched_alias": candidate.get("alias") if candidate.get("kind") == "alias" else None,
            "occurrences": candidate.get("occurrences", 0),
            "campus_id": candidate.get("campus_id"),
            "college_id": candidate.get("college_id"),
            "school_id": candidate.get("school_id"),
        }
        ranked.append(rec)
    return sorted(ranked, key=lambda item: (-item.get("score", 0), (item.get("programme_name") or "").lower()))[:3]

async def record_submission(db: AsyncSession, *, user_id: Optional[str], institution_id: str, campus_id: str, college_id: str, school_id: str, raw_name: str, source: str = "profile", accepted_programme_id: Optional[str] = None, accepted_candidate_id: Optional[int] = None) -> AcademicProgrammeSubmission:
    normalized, tokens = normalize_programme_name(raw_name)
    now = datetime.now(timezone.utc)
    row = AcademicProgrammeSubmission(institution_id=institution_id, campus_id=campus_id, college_id=college_id, school_id=school_id, raw_programme_name=raw_name.strip(), normalized_programme_name=normalized, normalized_tokens=tokens, submitted_by_user_id=user_id, status="accepted_by_student" if accepted_programme_id or accepted_candidate_id else "unlisted", source=source, accepted_programme_id=accepted_programme_id, accepted_candidate_id=accepted_candidate_id, created_at=now, updated_at=now)
    db.add(row); await db.flush()
    return row
