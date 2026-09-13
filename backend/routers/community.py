import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.auth import User
from models.comments import Comments
from models.notifications import Notifications
from models.paper_interactions import PaperInteractions
from models.papers import Papers
from models.books import Author, Book, BookAuthor, BookCourse, BookModule, Module
from models.courses import Course
from models.reports import Reports
from models.solutions import Solutions
from models.user_profiles import User_profiles
from routers.notifications import create_notification
from schemas.auth import UserResponse
from services.authorization import require_upload_permission
from services.site_access import require_resource_upload
from services.auth import ensure_user_profile_record
from services.academic_taxonomy import context_names, validate_context
from services.programme_discovery import normalize_programme_name, record_submission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/community", tags=["community"])

AUTO_HIDE_REPORT_THRESHOLD = 3
TRUST_SCORE_FOR_VERIFIED_CONTRIBUTOR = 50
DOWNLOAD_INTEREST_WEIGHT = 3
VIEW_INTEREST_WEIGHT = 1
RECENT_INTERACTION_LIMIT = 8
RECOMMENDATION_LIMIT = 8
ROLE_VERIFICATION_MAP = {
    "admin": "verified",
    "content_manager": "verified",
    "cp": "verified",
    "lecturer": "verified",
    "verified_contributor": "community",
}


class CommunityCommentCreate(BaseModel):
    content: str = Field(min_length=1)
    parent_id: Optional[int] = None


class CommunitySolutionCreate(BaseModel):
    content: str = Field(min_length=1)


class CommunityReportCreate(BaseModel):
    reason: str = Field(min_length=3)


class CommunityPaperCreate(BaseModel):
    title: str
    course_code: str
    course_name: str
    college: Optional[str] = None
    department: Optional[str] = None
    year: int
    paper_type: str
    lecturer: Optional[str] = None
    description: Optional[str] = None
    file_key: Optional[str] = None
    solution_key: Optional[str] = None
    verification_status: str = "unverified"
    download_count: int = 0
    report_count: int = 0
    is_hidden: bool = False
    institution_id: Optional[str] = None
    campus_id: Optional[str] = None
    college_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_department_id: Optional[str] = None
    programme_id: Optional[str] = None
    year_of_study: Optional[str] = None
    semester: Optional[str] = None
    examination_session: Optional[str] = None
    programme_name_other: Optional[str] = None
    academic_programme_status: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: int
    user_id: str
    display_name: str
    role: str
    trust_score: int
    upload_count: int
    download_count: int
    institution_type: Optional[str] = None
    university_name: Optional[str] = None
    ur_student_code: Optional[str] = None
    ur_verification_status: Optional[str] = None
    profile_picture_key: Optional[str] = None
    phone_number: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    institution_id: Optional[str] = None
    campus_id: Optional[str] = None
    college_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_department_id: Optional[str] = None
    programme_id: Optional[str] = None
    programme_name_other: Optional[str] = None
    academic_programme_status: Optional[str] = None
    programme_name_normalized: Optional[str] = None
    year_of_study: Optional[str] = None
    bio: Optional[str] = None
    requested_role: Optional[str] = None
    requested_role_status: Optional[str] = None
    account_status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PublicUserProfileResponse(BaseModel):
    user_id: str
    display_name: str
    role: str
    trust_score: int
    upload_count: int
    download_count: int
    institution_type: Optional[str] = None
    university_name: Optional[str] = None
    ur_verification_status: Optional[str] = None
    profile_picture_key: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    year_of_study: Optional[str] = None
    bio: Optional[str] = None
    created_at: Optional[datetime] = None


class LeaderboardResponse(BaseModel):
    items: list[UserProfileResponse]


async def _resource_summary(db: AsyncSession, resource, kind: str) -> dict:
    """Stable, deliberately typed representation used by dashboards and profiles."""
    if kind == "paper":
        return {
            "id": resource.id, "type": "paper", "title": resource.title,
            "created_at": resource.created_at, "uploader_id": resource.user_id,
            "downloads": resource.download_count or 0, "visibility": "public" if not resource.is_hidden else "hidden",
            "verification_status": resource.verification_status,
            "metadata": {"course_code": resource.course_code, "course_name": resource.course_name,
                         "year": resource.year, "year_of_study": getattr(resource, "year_of_study", None),
                         "semester": getattr(resource, "semester", None), "examination_session": getattr(resource, "examination_session", None),
                         "paper_type": resource.paper_type, "lecturer": resource.lecturer},
        }
    authors = (await db.execute(select(Author.name).join(BookAuthor, BookAuthor.author_id == Author.id).where(BookAuthor.book_id == resource.id))).scalars().all()
    courses = (await db.execute(select(Course).join(BookCourse, BookCourse.course_id == Course.id).where(BookCourse.book_id == resource.id))).scalars().all()
    modules = (await db.execute(select(Module).join(BookModule, BookModule.module_id == Module.id).where(BookModule.book_id == resource.id))).scalars().all()
    return {
        "id": resource.id, "type": "book", "title": resource.title,
        "created_at": resource.created_at, "uploader_id": resource.uploaded_by,
        "downloads": resource.download_count or 0, "visibility": resource.visibility,
        # Books do not have the Paper verification model; expose their actual publication state.
        "verification_status": None,
        "metadata": {"authors": authors, "language": resource.language, "edition": resource.edition,
                     "year_of_study": getattr(resource, "year_of_study", None), "semester": getattr(resource, "semester", None),
                     "status": resource.status, "file_name": resource.file_name,
                     "courses": [{"id": c.id, "code": c.code, "name": c.name} for c in courses],
                     "modules": [{"id": m.id, "code": m.code, "name": m.name} for m in modules]},
    }


async def _owned_resources(db: AsyncSession, user_id: str) -> list[dict]:
    papers = (await db.execute(select(Papers).where(Papers.user_id == user_id))).scalars().all()
    books = (await db.execute(select(Book).where(Book.uploaded_by == user_id))).scalars().all()
    resources = [await _resource_summary(db, paper, "paper") for paper in papers]
    resources.extend([await _resource_summary(db, book, "book") for book in books])
    return sorted(resources, key=lambda item: item["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


class UserProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    institution_type: Optional[str] = None
    university_name: Optional[str] = None
    ur_student_code: Optional[str] = None
    profile_picture_key: Optional[str] = None
    phone_number: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    institution_id: Optional[str] = None
    campus_id: Optional[str] = None
    college_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_department_id: Optional[str] = None
    programme_id: Optional[str] = None
    programme_name_other: Optional[str] = None
    year_of_study: Optional[str] = None
    bio: Optional[str] = None


class PaperInteractionResponse(BaseModel):
    paper_id: int
    view_count: int
    download_count: int
    interest_score: int
    last_interacted_at: Optional[datetime] = None


class RecommendationPaperResponse(BaseModel):
    id: int
    user_id: str
    title: str
    course_code: str
    course_name: str
    college: str
    department: str
    year: int
    paper_type: str
    lecturer: Optional[str] = None
    description: Optional[str] = None
    file_key: Optional[str] = None
    solution_key: Optional[str] = None
    verification_status: str
    download_count: int = 0
    report_count: int = 0
    is_hidden: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PersonalizedRecommendationsResponse(BaseModel):
    recently_viewed: list[RecommendationPaperResponse]
    recommended: list[RecommendationPaperResponse]
    top_departments: list[str]
    top_paper_types: list[str]
    top_course_codes: list[str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_profile(profile: User_profiles) -> dict:
    """Keep dashboard/profile aggregates independent from ORM serialization details."""
    return {column.name: getattr(profile, column.name) for column in User_profiles.__table__.columns}


async def _get_profile(db: AsyncSession, user_id: str) -> Optional[User_profiles]:
    result = await db.execute(select(User_profiles).where(User_profiles.user_id == user_id))
    return result.scalar_one_or_none()


async def _get_paper_interaction(db: AsyncSession, user_id: str, paper_id: int) -> Optional[PaperInteractions]:
    result = await db.execute(
        select(PaperInteractions).where(
            PaperInteractions.user_id == user_id,
            PaperInteractions.paper_id == paper_id,
        )
    )
    return result.scalar_one_or_none()


async def _record_paper_interaction(db: AsyncSession, user_id: str, paper_id: int, interaction_type: str) -> PaperInteractions:
    interaction = await _get_paper_interaction(db, user_id, paper_id)
    now = _utcnow()
    if not interaction:
        interaction = PaperInteractions(
            user_id=user_id,
            paper_id=paper_id,
            view_count=0,
            download_count=0,
            interest_score=0,
            created_at=now,
        )
        db.add(interaction)

    if interaction_type == "view":
        interaction.view_count = (interaction.view_count or 0) + 1
        interaction.last_viewed_at = now
        interaction.interest_score = (interaction.interest_score or 0) + VIEW_INTEREST_WEIGHT
    elif interaction_type == "download":
        interaction.download_count = (interaction.download_count or 0) + 1
        interaction.last_downloaded_at = now
        interaction.interest_score = (interaction.interest_score or 0) + DOWNLOAD_INTEREST_WEIGHT
    else:
        raise ValueError("Unsupported interaction type")

    interaction.last_interacted_at = now
    await db.flush()
    return interaction


def _serialize_paper(paper: Papers) -> dict:
    return {
        "id": paper.id,
        "user_id": paper.user_id,
        "title": paper.title,
        "course_code": paper.course_code,
        "course_name": paper.course_name,
        "college": paper.college,
        "department": paper.department,
        "year": paper.year,
        "paper_type": paper.paper_type,
        "lecturer": paper.lecturer,
        "description": paper.description,
        "file_key": paper.file_key,
        "solution_key": paper.solution_key,
        "verification_status": paper.verification_status,
        "download_count": paper.download_count or 0,
        "report_count": paper.report_count or 0,
        "is_hidden": bool(paper.is_hidden),
        "created_at": paper.created_at,
    }


async def _ensure_profile(db: AsyncSession, current_user: UserResponse) -> User_profiles:
    profile = await _get_profile(db, str(current_user.id))
    if profile:
        return profile

    display_name = current_user.name or current_user.email or f"Student {current_user.id}"
    role = current_user.role if current_user.role in ROLE_VERIFICATION_MAP or current_user.role == "normal" else "normal"
    profile = User_profiles(
        user_id=str(current_user.id),
        display_name=display_name,
        role=role,
        trust_score=100 if role == "admin" else 0,
        upload_count=0,
        download_count=0,
        institution_type=None,
        university_name=None,
        ur_student_code=None,
        ur_verification_status="not_requested",
        profile_picture_key=None,
        phone_number=None,
        college_name=None,
        department_name=None,
        year_of_study=None,
        bio=None,
        requested_role=None,
        requested_role_status="none",
        account_status="active",
        created_at=_utcnow(),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def _verification_for_profile(profile: User_profiles) -> str:
    if profile.role in ROLE_VERIFICATION_MAP:
        return ROLE_VERIFICATION_MAP[profile.role]
    if (profile.trust_score or 0) >= TRUST_SCORE_FOR_VERIFIED_CONTRIBUTOR:
        return "community"
    return "unverified"


async def _refresh_trust_role(profile: User_profiles, db: AsyncSession) -> None:
    trust_score = profile.trust_score or 0
    if profile.role == "normal" and trust_score >= TRUST_SCORE_FOR_VERIFIED_CONTRIBUTOR:
        profile.role = "verified_contributor"
    elif profile.role == "verified_contributor" and trust_score < TRUST_SCORE_FOR_VERIFIED_CONTRIBUTOR:
        profile.role = "normal"
    await db.flush()


def _score_recommendation(candidate: Papers, preferences: dict[str, dict[str, float]]) -> float:
    score = 0.0

    score += preferences["course_code"].get(candidate.course_code, 0.0) * 4.0
    score += preferences["department"].get(candidate.department, 0.0) * 2.4
    score += preferences["college"].get(candidate.college, 0.0) * 1.4
    score += preferences["paper_type"].get(candidate.paper_type, 0.0) * 1.8

    if candidate.lecturer:
        score += preferences["lecturer"].get(candidate.lecturer, 0.0) * 1.0

    if candidate.solution_key:
        score += 0.4
    if candidate.verification_status == "verified":
        score += 0.4
    if candidate.verification_status == "community":
        score += 0.2

    score += min((candidate.download_count or 0), 100) / 100.0
    return score


async def _build_personalized_recommendations(
    db: AsyncSession,
    user_id: str,
) -> PersonalizedRecommendationsResponse:
    interaction_result = await db.execute(
        select(PaperInteractions)
        .where(PaperInteractions.user_id == user_id)
        .order_by(desc(func.coalesce(PaperInteractions.last_interacted_at, PaperInteractions.created_at)))
        .limit(40)
    )
    interactions = interaction_result.scalars().all()

    if not interactions:
        fallback_result = await db.execute(
            select(Papers)
            .where(func.coalesce(Papers.is_hidden, False).is_(False))
            .order_by(
                desc(func.coalesce(Papers.download_count, 0)),
                desc(Papers.created_at),
            )
            .limit(RECOMMENDATION_LIMIT)
        )
        fallback_papers = fallback_result.scalars().all()
        return PersonalizedRecommendationsResponse(
            recently_viewed=[],
            recommended=[RecommendationPaperResponse(**_serialize_paper(paper)) for paper in fallback_papers],
            top_departments=[],
            top_paper_types=[],
            top_course_codes=[],
        )

    paper_ids = [interaction.paper_id for interaction in interactions]
    papers_result = await db.execute(select(Papers).where(Papers.id.in_(paper_ids)))
    papers_by_id = {paper.id: paper for paper in papers_result.scalars().all()}

    preferences: dict[str, dict[str, float]] = {
        "course_code": {},
        "department": {},
        "college": {},
        "paper_type": {},
        "lecturer": {},
    }
    recent_pairs: list[tuple[PaperInteractions, Papers]] = []

    for index, interaction in enumerate(interactions):
        paper = papers_by_id.get(interaction.paper_id)
        if not paper or paper.is_hidden:
            continue

        recent_pairs.append((interaction, paper))
        recency_multiplier = max(1.0, 3.0 - (index * 0.12))
        interaction_weight = max(1.0, float(interaction.interest_score or 0)) * recency_multiplier

        preferences["course_code"][paper.course_code] = preferences["course_code"].get(paper.course_code, 0.0) + interaction_weight
        preferences["department"][paper.department] = preferences["department"].get(paper.department, 0.0) + interaction_weight
        preferences["college"][paper.college] = preferences["college"].get(paper.college, 0.0) + (interaction_weight * 0.75)
        preferences["paper_type"][paper.paper_type] = preferences["paper_type"].get(paper.paper_type, 0.0) + (interaction_weight * 0.85)
        if paper.lecturer:
            preferences["lecturer"][paper.lecturer] = preferences["lecturer"].get(paper.lecturer, 0.0) + (interaction_weight * 0.55)

    recently_viewed = [
        RecommendationPaperResponse(**_serialize_paper(paper))
        for interaction, paper in recent_pairs
        if (interaction.view_count or 0) > 0
    ][:RECENT_INTERACTION_LIMIT]

    excluded_paper_ids = {paper.id for _, paper in recent_pairs}
    candidate_result = await db.execute(
        select(Papers)
        .where(func.coalesce(Papers.is_hidden, False).is_(False))
        .order_by(
            desc(Papers.created_at),
            desc(func.coalesce(Papers.download_count, 0)),
        )
        .limit(300)
    )
    candidates = [
        paper
        for paper in candidate_result.scalars().all()
        if paper.id not in excluded_paper_ids
    ]

    scored_candidates = sorted(
        candidates,
        key=lambda paper: (_score_recommendation(paper, preferences), paper.created_at or _utcnow()),
        reverse=True,
    )

    recommended = [
        RecommendationPaperResponse(**_serialize_paper(paper))
        for paper in scored_candidates[:RECOMMENDATION_LIMIT]
    ]

    def top_keys(bucket: str) -> list[str]:
        return [item[0] for item in sorted(preferences[bucket].items(), key=lambda item: item[1], reverse=True)[:3]]

    return PersonalizedRecommendationsResponse(
        recently_viewed=recently_viewed,
        recommended=recommended,
        top_departments=top_keys("department"),
        top_paper_types=top_keys("paper_type"),
        top_course_codes=top_keys("course_code"),
    )


@router.get("/profile", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _ensure_profile(db, current_user)


@router.get("/dashboard")
async def get_dashboard(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authoritative dashboard aggregate.  Never infer a resource type in clients."""
    profile = await _ensure_profile(db, current_user)
    resources = await _owned_resources(db, str(current_user.id))
    paper_count = sum(item["type"] == "paper" for item in resources)
    book_count = sum(item["type"] == "book" for item in resources)
    verified_papers = sum(item["type"] == "paper" and item["verification_status"] == "verified" for item in resources)
    total_downloads = sum(item["downloads"] for item in resources)
    leaderboard = (await db.execute(select(User_profiles).order_by(
        desc(func.coalesce(User_profiles.trust_score, 0)),
        desc(func.coalesce(User_profiles.upload_count, 0)),
    ).limit(10))).scalars().all()
    return {
        "stats": {"total_uploads": len(resources), "paper_count": paper_count, "book_count": book_count,
                  "total_downloads": total_downloads, "verified_paper_count": verified_papers,
                  "average_downloads": round(total_downloads / len(resources)) if resources else 0},
        "uploaded_resources": resources,
        "contribution": {"upload_count": profile.upload_count or 0, "trust_score": profile.trust_score or 0,
                           "role": profile.role},
        "leaderboard": [_serialize_profile(row) for row in leaderboard],
    }


@router.get("/profiles/{user_id}", response_model=PublicUserProfileResponse)
async def get_public_profile(user_id: str, db: AsyncSession = Depends(get_db)):
    profile = await _get_profile(db, user_id)
    if not profile:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user:
            display_name = user.name or (user.email.split('@')[0] if user.email else None) or f"Student {user_id}"
            return PublicUserProfileResponse(
                user_id=str(user.id),
                display_name=display_name,
                role=user.role or "user",
                trust_score=100 if user.role == "admin" else 0,
                upload_count=0,
                download_count=0,
                institution_type=None,
                university_name=None,
                ur_verification_status="not_requested",
                profile_picture_key=None,
                college_name=None,
                department_name=None,
                year_of_study=None,
                bio=None,
                created_at=user.created_at,
            )
        raise HTTPException(status_code=404, detail="User profile not found")

    return PublicUserProfileResponse(
        user_id=profile.user_id,
        display_name=profile.display_name,
        role=profile.role,
        trust_score=profile.trust_score or 0,
        upload_count=profile.upload_count or 0,
        download_count=profile.download_count or 0,
        institution_type=profile.institution_type,
        university_name=profile.university_name,
        ur_verification_status=profile.ur_verification_status,
        profile_picture_key=profile.profile_picture_key,
        college_name=profile.college_name,
        department_name=profile.department_name,
        year_of_study=profile.year_of_study,
        bio=profile.bio,
        created_at=profile.created_at,
    )


@router.get("/profiles/{user_id}/resources")
async def get_public_profile_resources(user_id: str, db: AsyncSession = Depends(get_db)):
    """Only resources visible to the public; private/draft owner resources remain private."""
    profile = await _get_profile(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    papers = (await db.execute(select(Papers).where(Papers.user_id == user_id, Papers.is_hidden.is_not(True)))).scalars().all()
    books = (await db.execute(select(Book).where(Book.uploaded_by == user_id, Book.status == "active", Book.visibility == "public"))).scalars().all()
    items = [await _resource_summary(db, paper, "paper") for paper in papers]
    items.extend([await _resource_summary(db, book, "book") for book in books])
    return {"items": sorted(items, key=lambda item: item["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)}


@router.patch("/profile", response_model=UserProfileResponse)
async def update_my_profile(
    payload: UserProfileUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == str(current_user.id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        data = payload.model_dump(exclude_unset=True)
        current = await _get_profile(db, str(current_user.id))
        ids = {key: data.get(key, getattr(current, key, None)) for key in ("institution_id", "campus_id", "college_id", "school_id", "programme_id")}
        validate_context(**ids, academic_department_id=data.get("academic_department_id", getattr(current, "academic_department_id", None)))
        if data.get("programme_id", getattr(current, "programme_id", None)) == "other":
            other_name = data.get("programme_name_other", getattr(current, "programme_name_other", None))
            if not other_name: raise ValueError("Enter your programme name")
            normalize_programme_name(other_name)
        if any(ids.values()): data.update({k: v for k, v in context_names(ids["campus_id"], ids["college_id"], ids["school_id"], ids["programme_id"]).items() if v})
        profile = await ensure_user_profile_record(db, user, data)
        if profile.programme_id == "other" and profile.programme_name_other:
            submission = await record_submission(db, user_id=str(current_user.id), institution_id=profile.institution_id or "ur", campus_id=profile.campus_id, college_id=profile.college_id, school_id=profile.school_id, raw_name=profile.programme_name_other)
            profile.programme_submission_id = submission.id
            profile.programme_name_normalized = submission.normalized_programme_name
            profile.academic_programme_status = submission.status
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User_profiles).order_by(
            desc(func.coalesce(User_profiles.trust_score, 0)),
            desc(func.coalesce(User_profiles.upload_count, 0)),
        ).limit(10)
    )
    return {"items": result.scalars().all()}


@router.post("/papers/{paper_id}/record-view", response_model=PaperInteractionResponse)
async def record_view(
    paper_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper or paper.is_hidden:
        raise HTTPException(status_code=404, detail="Paper not found")

    await _ensure_profile(db, current_user)
    interaction = await _record_paper_interaction(db, str(current_user.id), paper_id, "view")
    await db.commit()
    await db.refresh(interaction)
    return PaperInteractionResponse(
        paper_id=paper_id,
        view_count=interaction.view_count or 0,
        download_count=interaction.download_count or 0,
        interest_score=interaction.interest_score or 0,
        last_interacted_at=interaction.last_interacted_at,
    )


@router.get("/papers/recommendations", response_model=PersonalizedRecommendationsResponse)
async def get_personalized_recommendations(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_profile(db, current_user)
    return await _build_personalized_recommendations(db, str(current_user.id))


@router.post("/papers")
async def create_paper(
    payload: CommunityPaperCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_resource_upload(db, current_user, "paper")
    validate_context(payload.institution_id, payload.campus_id, payload.college_id, payload.school_id, payload.programme_id, payload.academic_department_id)
    if payload.programme_id == "other":
        if not payload.programme_name_other: raise HTTPException(400, "Enter your programme name")
        normalize_programme_name(payload.programme_name_other)
    profile = await _ensure_profile(db, current_user)
    names = context_names(payload.campus_id, payload.college_id, payload.school_id, payload.programme_id)
    if not (names["college_name"] or payload.college) or not (names["department_name"] or payload.department):
        raise HTTPException(status_code=400, detail="A complete academic context or legacy college and department is required")
    submission = None
    if payload.programme_id == "other" and payload.programme_name_other:
        submission = await record_submission(db, user_id=str(current_user.id), institution_id=payload.institution_id or "ur", campus_id=payload.campus_id, college_id=payload.college_id, school_id=payload.school_id, raw_name=payload.programme_name_other)
    paper = Papers(
        user_id=str(current_user.id),
        title=payload.title,
        course_code=payload.course_code,
        course_name=payload.course_name,
        college=names["college_name"] or payload.college,
        department=names["department_name"] or payload.department,
        institution_id=payload.institution_id, campus_id=payload.campus_id, college_id=payload.college_id, school_id=payload.school_id, academic_department_id=payload.academic_department_id, programme_id=payload.programme_id, programme_submission_id=submission.id if submission else None, programme_name_other=payload.programme_name_other, programme_name_normalized=submission.normalized_programme_name if submission else None, academic_programme_status=submission.status if submission else None, semester=payload.semester, examination_session=payload.examination_session,
        year_of_study=payload.year_of_study,
        year=payload.year,
        paper_type=payload.paper_type,
        lecturer=payload.lecturer,
        description=payload.description,
        file_key=payload.file_key,
        solution_key=payload.solution_key,
        verification_status=_verification_for_profile(profile),
        download_count=0,
        report_count=0,
        is_hidden=False,
        created_at=_utcnow(),
    )
    db.add(paper)
    profile.upload_count = (profile.upload_count or 0) + 1
    profile.trust_score = (profile.trust_score or 0) + 2
    await _refresh_trust_role(profile, db)
    await db.flush()
    await create_notification(
        db,
        str(current_user.id),
        "Upload submitted",
        f'"{paper.title}" was submitted successfully and is awaiting community review.',
        "upload",
        "paper",
        paper.id,
    )
    await db.commit()
    await db.refresh(paper)
    return paper


@router.post("/papers/{paper_id}/comments")
async def add_comment(
    paper_id: int,
    payload: CommunityCommentCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    await _ensure_profile(db, current_user)
    comment = Comments(
        user_id=str(current_user.id),
        paper_id=paper_id,
        content=payload.content.strip(),
        parent_id=payload.parent_id,
        upvotes=0,
        created_at=_utcnow(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.post("/books/{book_id}/comments")
async def add_book_comment(
    book_id: int,
    payload: CommunityCommentCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await db.get(Book, book_id)
    if not book or book.status != "active" or book.visibility != "public":
        raise HTTPException(status_code=404, detail="Book not found")

    await _ensure_profile(db, current_user)
    comment = Comments(
        user_id=str(current_user.id),
        book_id=book_id,
        content=payload.content.strip(),
        parent_id=payload.parent_id,
        upvotes=0,
        created_at=_utcnow(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.post("/papers/{paper_id}/solutions")
async def add_solution(
    paper_id: int,
    payload: CommunitySolutionCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    profile = await _ensure_profile(db, current_user)
    solution = Solutions(
        user_id=str(current_user.id),
        paper_id=paper_id,
        content=payload.content.strip(),
        upvotes=0,
        is_best=False,
        created_at=_utcnow(),
    )
    profile.trust_score = (profile.trust_score or 0) + 1
    await _refresh_trust_role(profile, db)
    db.add(solution)
    await db.commit()
    await db.refresh(solution)
    return solution


@router.post("/papers/{paper_id}/report")
async def report_paper(
    paper_id: int,
    payload: CommunityReportCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = await db.execute(
        select(Reports).where(Reports.paper_id == paper_id, Reports.user_id == str(current_user.id))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You have already reported this paper")

    report = Reports(
        user_id=str(current_user.id),
        paper_id=paper_id,
        reason=payload.reason.strip(),
        status="pending",
        created_at=_utcnow(),
    )
    db.add(report)

    paper.report_count = (paper.report_count or 0) + 1
    if paper.report_count >= AUTO_HIDE_REPORT_THRESHOLD:
        paper.is_hidden = True

    owner_profile = await _get_profile(db, paper.user_id)
    if owner_profile:
        owner_profile.trust_score = max(0, (owner_profile.trust_score or 0) - 5)
        await _refresh_trust_role(owner_profile, db)
    await create_notification(
        db,
        paper.user_id,
        "Paper reported",
        f'"{paper.title}" was reported by the community. Moderators may review it soon.',
        "report",
        "paper",
        paper.id,
    )

    await db.commit()
    await db.refresh(report)
    return {
        "report": report,
        "paper": {
            "id": paper.id,
            "report_count": paper.report_count,
            "is_hidden": paper.is_hidden,
        },
    }


@router.post("/solutions/{solution_id}/upvote")
async def upvote_solution(
    solution_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    solution = await db.get(Solutions, solution_id)
    if not solution:
        raise HTTPException(status_code=404, detail="Solution not found")

    solution.upvotes = (solution.upvotes or 0) + 1
    if solution.upvotes >= 5:
        solution.is_best = True

    profile = await _get_profile(db, solution.user_id)
    if profile:
        profile.trust_score = (profile.trust_score or 0) + 2
        await _refresh_trust_role(profile, db)

    await db.commit()
    await db.refresh(solution)
    return solution


@router.post("/comments/{comment_id}/upvote")
async def upvote_comment(
    comment_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comment = await db.get(Comments, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment.upvotes = (comment.upvotes or 0) + 1
    profile = await _get_profile(db, comment.user_id)
    if profile:
        profile.trust_score = (profile.trust_score or 0) + 1
        await _refresh_trust_role(profile, db)

    await db.commit()
    await db.refresh(comment)
    return comment


@router.post("/papers/{paper_id}/record-download")
async def record_download(
    paper_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper or paper.is_hidden:
        raise HTTPException(status_code=404, detail="Paper not found")

    profile = await _ensure_profile(db, current_user)
    profile.download_count = (profile.download_count or 0) + 1
    paper.download_count = (paper.download_count or 0) + 1
    await _record_paper_interaction(db, str(current_user.id), paper_id, "download")
    await db.commit()
    return {"download_count": paper.download_count}
