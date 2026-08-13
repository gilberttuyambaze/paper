import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_management_user
from models.auth import User
from models.comments import Comments
from models.notifications import Notifications
from models.papers import Papers
from models.reports import Reports
from models.solutions import Solutions
from models.user_profiles import User_profiles
from models.academic_programme_submissions import AcademicProgrammeAlias, AcademicProgrammeSubmission
from services.academic_taxonomy import NODES
from routers.notifications import create_notification
from schemas.auth import UserResponse
from services.programme_discovery import find_programme_matches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/hub", tags=["admin-hub"])
MANAGEMENT_ROLES = {"normal", "verified_contributor", "cp", "lecturer", "content_manager", "admin"}
REQUESTABLE_ROLES = {"cp", "lecturer"}
ACCOUNT_STATUSES = {"active", "suspended", "banned"}
UR_VERIFICATION_STATUSES = {"not_requested", "pending", "verified", "rejected"}
INSTITUTION_TYPES = {"ur_student", "other_university"}


class AdminPaperModerationRequest(BaseModel):
    verification_status: Optional[str] = None
    is_hidden: Optional[bool] = None


class AdminUserUpdateRequest(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    trust_score: Optional[int] = None
    account_status: Optional[str] = None
    ur_verification_status: Optional[str] = None
    institution_type: Optional[str] = None
    university_name: Optional[str] = None
    ur_student_code: Optional[str] = None
    profile_picture_key: Optional[str] = None
    phone_number: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    year_of_study: Optional[str] = None
    bio: Optional[str] = None
    suspension_reason: Optional[str] = None
    suspended_until: Optional[datetime] = None


class AdminReportUpdateRequest(BaseModel):
    status: str
    hide_paper: Optional[bool] = None
    verification_status: Optional[str] = None


class AdminRoleRequestReviewRequest(BaseModel):
    action: str

class ProgrammeCandidateReviewRequest(BaseModel):
    action: str
    programme_id: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None

@router.get("/programme-candidates")
async def list_programme_candidates(_current_user: UserResponse = Depends(get_management_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AcademicProgrammeSubmission.normalized_programme_name, AcademicProgrammeSubmission.campus_id, AcademicProgrammeSubmission.college_id, AcademicProgrammeSubmission.school_id, func.count(AcademicProgrammeSubmission.id).label("occurrences")).where(AcademicProgrammeSubmission.status.notin_(["rejected", "merged"])).group_by(AcademicProgrammeSubmission.normalized_programme_name, AcademicProgrammeSubmission.campus_id, AcademicProgrammeSubmission.college_id, AcademicProgrammeSubmission.school_id).order_by(desc("occurrences")))).all()
    return {"items": [{"normalized_programme_name": row.normalized_programme_name, "campus_id": row.campus_id, "college_id": row.college_id, "school_id": row.school_id, "occurrences": row.occurrences} for row in rows]}


@router.get("/programme-candidates/detailed")
async def list_programme_candidates_detailed(_current_user: UserResponse = Depends(get_management_user), db: AsyncSession = Depends(get_db)):
    # Aggregate submissions and include a best-match recommendation using the matching service
    rows = (await db.execute(select(AcademicProgrammeSubmission.normalized_programme_name, AcademicProgrammeSubmission.campus_id, AcademicProgrammeSubmission.college_id, AcademicProgrammeSubmission.school_id, func.count(AcademicProgrammeSubmission.id).label("occurrences")).where(AcademicProgrammeSubmission.status.notin_("rejected")).group_by(AcademicProgrammeSubmission.normalized_programme_name, AcademicProgrammeSubmission.campus_id, AcademicProgrammeSubmission.college_id, AcademicProgrammeSubmission.school_id).order_by(desc("occurrences")))).all()
    items = []
    for row in rows:
        normalized = row.normalized_programme_name
        campus_id = row.campus_id
        college_id = row.college_id
        school_id = row.school_id
        # Use the discovery matcher to find best candidates for this normalized label
        try:
            matches = await find_programme_matches(db, institution_id="ur", campus_id=campus_id, college_id=college_id, school_id=school_id, raw_name=normalized)
        except Exception:
            matches = []
        best = matches[0] if matches else None
        items.append({
            "normalized_programme_name": normalized,
            "campus_id": campus_id,
            "college_id": college_id,
            "school_id": school_id,
            "occurrences": row.occurrences,
            "best_match": best,
            "matches": matches,
        })
    return {"items": items}


@router.get("/programme-candidates/{normalized}/submissions")
async def get_candidate_submissions(normalized: str, _current_user: UserResponse = Depends(get_management_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AcademicProgrammeSubmission).where(AcademicProgrammeSubmission.normalized_programme_name == normalized))).scalars().all()
    items = [
        {
            "id": r.id,
            "raw_programme_name": r.raw_programme_name,
            "normalized_programme_name": r.normalized_programme_name,
            "campus_id": r.campus_id,
            "college_id": r.college_id,
            "school_id": r.school_id,
            "submitted_by_user_id": None if r.submitted_by_user_id is None else str(r.submitted_by_user_id),
            "status": r.status,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
    return {"items": items}


class VerifyAliasRequest(BaseModel):
    normalized_programme_name: str
    campus_id: str
    college_id: str
    school_id: str
    programme_id: str


@router.post("/programme-candidates/verify-alias")
async def verify_programme_alias(payload: VerifyAliasRequest, current_user: UserResponse = Depends(get_management_user), db: AsyncSession = Depends(get_db)):
    # Ensure target programme exists
    if payload.programme_id not in NODES:
        raise HTTPException(400, "Unknown official programme")
    # Prevent duplicate verified alias for same normalized alias + programme
    existing = (await db.execute(select(AcademicProgrammeAlias).where(AcademicProgrammeAlias.normalized_alias == payload.normalized_programme_name))).scalars().first()
    if existing:
        raise HTTPException(409, "An alias for this normalized name already exists")
    alias = AcademicProgrammeAlias(programme_id=payload.programme_id, alias=payload.normalized_programme_name, normalized_alias=payload.normalized_programme_name, source="admin_verified", verified_by=str(current_user.id), created_at=_utcnow())
    db.add(alias)
    await db.commit(); await db.refresh(alias)
    return {"id": alias.id, "programme_id": alias.programme_id, "normalized_alias": alias.normalized_alias}


class RejectCandidatesRequest(BaseModel):
    normalized_programme_name: str
    campus_id: str
    college_id: str
    school_id: str


@router.post("/programme-candidates/reject")
async def reject_programme_candidates(payload: RejectCandidatesRequest, current_user: UserResponse = Depends(get_management_user), db: AsyncSession = Depends(get_db)):
    # Mark grouped submissions as rejected for this normalized label and context
    await db.execute(
        select(AcademicProgrammeSubmission).where(
            AcademicProgrammeSubmission.normalized_programme_name == payload.normalized_programme_name,
            AcademicProgrammeSubmission.campus_id == payload.campus_id,
            AcademicProgrammeSubmission.college_id == payload.college_id,
            AcademicProgrammeSubmission.school_id == payload.school_id,
        )
    )
    await db.execute(
        "UPDATE academic_programme_submissions SET status = :status, updated_at = :now WHERE normalized_programme_name = :name AND campus_id = :campus AND college_id = :college AND school_id = :school",
        {"status": "rejected", "now": _utcnow(), "name": payload.normalized_programme_name, "campus": payload.campus_id, "college": payload.college_id, "school": payload.school_id},
    )
    await db.commit()
    return {"status": "rejected"}

@router.post("/programme-submissions/{submission_id}/review")
async def review_programme_submission(submission_id: int, payload: ProgrammeCandidateReviewRequest, current_user: UserResponse = Depends(get_management_user), db: AsyncSession = Depends(get_db)):
    submission = await db.get(AcademicProgrammeSubmission, submission_id)
    if not submission: raise HTTPException(404, "Programme submission not found")
    if payload.action not in {"verify", "reject", "map", "merge"}: raise HTTPException(400, "Invalid review action")
    if payload.action in {"map", "merge"}:
        if not payload.programme_id or payload.programme_id not in NODES: raise HTTPException(400, "A verified taxonomy programme is required")
        submission.accepted_programme_id = payload.programme_id
        submission.status = "merged" if payload.action == "merge" else "verified"
        alias = AcademicProgrammeAlias(programme_id=payload.programme_id, alias=submission.raw_programme_name, normalized_alias=submission.normalized_programme_name, source="admin_review", verified_by=str(current_user.id), created_at=_utcnow())
        db.add(alias)
    else:
        submission.status = "candidate" if payload.action == "verify" else "rejected"
    submission.updated_at = _utcnow()
    await db.commit(); await db.refresh(submission)
    return {"id": submission.id, "status": submission.status, "programme_id": submission.accepted_programme_id}


def _serialize_user(profile: User_profiles, user: Optional[User]) -> dict:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "role": profile.role,
        "trust_score": profile.trust_score,
        "upload_count": profile.upload_count,
        "download_count": profile.download_count,
        "institution_type": profile.institution_type,
        "university_name": profile.university_name,
        "ur_student_code": profile.ur_student_code,
        "ur_verification_status": profile.ur_verification_status,
        "profile_picture_key": profile.profile_picture_key,
        "phone_number": profile.phone_number,
        "college_name": profile.college_name,
        "department_name": profile.department_name,
        "year_of_study": profile.year_of_study,
        "bio": profile.bio,
        "requested_role": profile.requested_role,
        "requested_role_status": profile.requested_role_status,
        "account_status": profile.account_status,
        "suspension_reason": profile.suspension_reason,
        "suspended_until": profile.suspended_until,
        "created_at": profile.created_at,
        "email": user.email if user else None,
        "name": user.name if user else profile.display_name,
        "auth_role": user.role if user else "user",
        "last_login": user.last_login if user else None,
    }


def _ensure_role_assignment_allowed(actor: UserResponse, target_profile: User_profiles, requested_role: str) -> None:
    if requested_role not in MANAGEMENT_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role selection")
    if actor.role != "admin" and (requested_role == "admin" or target_profile.role == "admin"):
        raise HTTPException(status_code=403, detail="Only admins can modify administrator accounts")


@router.get("/overview")
async def get_overview(
    _current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    total_papers = await db.scalar(select(func.count(Papers.id)))
    hidden_papers = await db.scalar(select(func.count(Papers.id)).where(Papers.is_hidden.is_(True)))
    verified_papers = await db.scalar(select(func.count(Papers.id)).where(Papers.verification_status == "verified"))
    total_reports = await db.scalar(select(func.count(Reports.id)))
    pending_reports = await db.scalar(select(func.count(Reports.id)).where(Reports.status == "pending"))
    total_users = await db.scalar(select(func.count(User_profiles.id)))
    pending_role_requests = await db.scalar(
        select(func.count(User_profiles.id)).where(
            User_profiles.requested_role.in_(REQUESTABLE_ROLES),
            User_profiles.requested_role_status == "pending",
        )
    )

    top_contributors = await db.execute(
        select(User_profiles).order_by(
            desc(func.coalesce(User_profiles.upload_count, 0)),
            desc(func.coalesce(User_profiles.trust_score, 0)),
        ).limit(5)
    )

    recent_reports = await db.execute(
        select(Reports).order_by(desc(Reports.created_at)).limit(20)
    )

    return {
        "stats": {
            "total_papers": total_papers or 0,
            "hidden_papers": hidden_papers or 0,
            "verified_papers": verified_papers or 0,
            "total_reports": total_reports or 0,
            "pending_reports": pending_reports or 0,
            "total_users": total_users or 0,
            "pending_role_requests": pending_role_requests or 0,
        },
        "top_contributors": top_contributors.scalars().all(),
        "recent_reports": recent_reports.scalars().all(),
    }


@router.get("/users")
async def list_users(
    search: Optional[str] = Query(default=None),
    _current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(User_profiles, User)
        .join(User, User.id == User_profiles.user_id, isouter=True)
        .order_by(
        desc(func.coalesce(User_profiles.trust_score, 0)),
        desc(func.coalesce(User_profiles.upload_count, 0)),
        )
    )
    if search:
        like_value = f"%{search.lower()}%"
        query = query.where(
            func.lower(User_profiles.display_name).like(like_value)
            | func.lower(User_profiles.user_id).like(like_value)
            | func.lower(User_profiles.role).like(like_value)
            | func.lower(func.coalesce(User_profiles.requested_role, "")).like(like_value)
            | func.lower(func.coalesce(User_profiles.requested_role_status, "")).like(like_value)
            | func.lower(func.coalesce(User_profiles.university_name, "")).like(like_value)
            | func.lower(func.coalesce(User_profiles.ur_student_code, "")).like(like_value)
            | func.lower(func.coalesce(User.email, "")).like(like_value)
        )

    result = await db.execute(query.limit(100))
    return {"items": [_serialize_user(profile, user) for profile, user in result.all()]}


@router.get("/role-requests")
async def list_role_requests(
    _current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User_profiles, User)
        .join(User, User.id == User_profiles.user_id, isouter=True)
        .where(
            User_profiles.requested_role.in_(REQUESTABLE_ROLES),
            User_profiles.requested_role_status == "pending",
        )
        .order_by(desc(User_profiles.created_at), desc(User_profiles.id))
    )
    return {"items": [_serialize_user(profile, user) for profile, user in result.all()]}


@router.patch("/users/{profile_id}")
async def update_user(
    profile_id: int,
    payload: AdminUserUpdateRequest,
    current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(User_profiles, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    user = await db.get(User, profile.user_id)

    if current_user.role != "admin" and profile.role == "admin":
        raise HTTPException(status_code=403, detail="Only admins can modify administrator accounts")

    if payload.email is not None:
        normalized_email = _normalize_email(payload.email)
        if not normalized_email:
            raise HTTPException(status_code=400, detail="Email cannot be empty")
        duplicate_user = await db.execute(select(User).where(User.email == normalized_email, User.id != profile.user_id))
        if duplicate_user.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another account already uses that email")
        if user:
            user.email = normalized_email

    if payload.display_name is not None:
        display_name = _normalize_text(payload.display_name)
        if not display_name:
            raise HTTPException(status_code=400, detail="Display name cannot be empty")
        profile.display_name = display_name
        if user:
            user.name = display_name

    if payload.role is not None:
        _ensure_role_assignment_allowed(current_user, profile, payload.role)
        profile.role = payload.role
        if payload.role in REQUESTABLE_ROLES:
            profile.requested_role = payload.role
            profile.requested_role_status = "approved"
        else:
            profile.requested_role = None
            profile.requested_role_status = "none"
        if user:
            user.role = "admin" if payload.role == "admin" else "user"
    if payload.trust_score is not None:
        profile.trust_score = payload.trust_score
    if payload.account_status is not None:
        if payload.account_status not in ACCOUNT_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid account status")
        profile.account_status = payload.account_status
    if payload.ur_verification_status is not None:
        if payload.ur_verification_status not in UR_VERIFICATION_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid UR verification status")
        profile.ur_verification_status = payload.ur_verification_status
    if payload.institution_type is not None:
        if payload.institution_type not in INSTITUTION_TYPES:
            raise HTTPException(status_code=400, detail="Invalid institution type")
        profile.institution_type = payload.institution_type
    if payload.university_name is not None:
        profile.university_name = _normalize_text(payload.university_name)
    if payload.ur_student_code is not None:
        profile.ur_student_code = _normalize_text(payload.ur_student_code)
    if payload.profile_picture_key is not None:
        profile.profile_picture_key = _normalize_text(payload.profile_picture_key)
    if payload.phone_number is not None:
        profile.phone_number = _normalize_text(payload.phone_number)
    if payload.college_name is not None:
        profile.college_name = _normalize_text(payload.college_name)
    if payload.department_name is not None:
        profile.department_name = _normalize_text(payload.department_name)
    if payload.year_of_study is not None:
        profile.year_of_study = _normalize_text(payload.year_of_study)
    if payload.bio is not None:
        profile.bio = _normalize_text(payload.bio)
    if payload.suspension_reason is not None:
        profile.suspension_reason = _normalize_text(payload.suspension_reason)
    if payload.suspended_until is not None:
        profile.suspended_until = payload.suspended_until

    await create_notification(
        db,
        profile.user_id,
        "Account updated",
        f"Your account status is now {profile.account_status or 'active'}, your role is {profile.role}, and UR verification is {profile.ur_verification_status or 'not_requested'}.",
        "account",
        "user_profile",
        profile.id,
    )

    await db.commit()
    await db.refresh(profile)
    if user:
        await db.refresh(user)
    return _serialize_user(profile, user)


@router.post("/role-requests/{profile_id}/review")
async def review_role_request(
    profile_id: int,
    payload: AdminRoleRequestReviewRequest,
    current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    action = payload.action.strip().lower()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Action must be approve or reject")

    profile = await db.get(User_profiles, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    requested_role = (profile.requested_role or "").strip().lower() or None
    requested_role_status = (profile.requested_role_status or "none").strip().lower()
    if requested_role not in REQUESTABLE_ROLES or requested_role_status != "pending":
        raise HTTPException(status_code=400, detail="This account has no pending CP or lecturer request")

    user = await db.get(User, profile.user_id)

    if action == "approve":
        _ensure_role_assignment_allowed(current_user, profile, requested_role)
        profile.role = requested_role
        profile.requested_role_status = "approved"
        if user:
            user.role = "user"
        await create_notification(
            db,
            profile.user_id,
            "Role request approved",
            f"Your request to become {requested_role.replace('_', ' ')} has been approved.",
            "role_request",
            "user_profile",
            profile.id,
        )
    else:
        profile.requested_role_status = "rejected"
        await create_notification(
            db,
            profile.user_id,
            "Role request declined",
            f"Your request to become {requested_role.replace('_', ' ')} was not approved yet. You can continue using your normal account.",
            "role_request",
            "user_profile",
            profile.id,
        )

    await db.commit()
    await db.refresh(profile)
    if user:
        await db.refresh(user)
    return _serialize_user(profile, user)


@router.delete("/users/{profile_id}")
async def delete_user(
    profile_id: int,
    current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(User_profiles, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    if current_user.id == profile.user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account from the management hub")

    if current_user.role != "admin" and profile.role == "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete administrator accounts")

    user = await db.get(User, profile.user_id)
    owned_paper_ids_result = await db.execute(select(Papers.id).where(Papers.user_id == profile.user_id))
    owned_paper_ids = [row[0] for row in owned_paper_ids_result.all()]

    if owned_paper_ids:
        await db.execute(delete(Reports).where(Reports.paper_id.in_(owned_paper_ids)))
        await db.execute(delete(Comments).where(Comments.paper_id.in_(owned_paper_ids)))
        await db.execute(delete(Solutions).where(Solutions.paper_id.in_(owned_paper_ids)))
        await db.execute(delete(Papers).where(Papers.id.in_(owned_paper_ids)))

    await db.execute(delete(Reports).where(Reports.user_id == profile.user_id))
    await db.execute(delete(Comments).where(Comments.user_id == profile.user_id))
    await db.execute(delete(Solutions).where(Solutions.user_id == profile.user_id))
    await db.execute(delete(Notifications).where(Notifications.user_id == profile.user_id))
    await db.delete(profile)
    if user:
        await db.delete(user)

    await db.commit()
    return {"deleted": True, "user_id": profile.user_id}


@router.patch("/papers/{paper_id}")
async def moderate_paper(
    paper_id: int,
    payload: AdminPaperModerationRequest,
    _current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Papers, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if payload.verification_status is not None:
        paper.verification_status = payload.verification_status
    if payload.is_hidden is not None:
        paper.is_hidden = payload.is_hidden

    await create_notification(
        db,
        paper.user_id,
        "Paper status updated",
        f'"{paper.title}" is now {paper.verification_status} and visibility is {"hidden" if paper.is_hidden else "visible"}.',
        "paper_status",
        "paper",
        paper.id,
    )

    await db.commit()
    await db.refresh(paper)
    return paper


@router.patch("/reports/{report_id}")
async def moderate_report(
    report_id: int,
    payload: AdminReportUpdateRequest,
    _current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Reports, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = payload.status
    paper = await db.get(Papers, report.paper_id)
    if paper:
        if payload.hide_paper is not None:
            paper.is_hidden = payload.hide_paper
        if payload.verification_status is not None:
            paper.verification_status = payload.verification_status
        await create_notification(
            db,
            paper.user_id,
            "Moderation update",
            f'A moderator reviewed a report on "{paper.title}". Status: {report.status}.',
            "moderation",
            "paper",
            paper.id,
        )

    await db.commit()
    await db.refresh(report)
    return report


@router.post("/profiles/sync")
async def sync_missing_profiles(
    _current_user: UserResponse = Depends(get_management_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Papers.user_id).distinct())
    paper_user_ids = {row[0] for row in result.all() if row[0]}

    created = 0
    for user_id in paper_user_ids:
        existing = await db.execute(select(User_profiles).where(User_profiles.user_id == user_id))
        if existing.scalar_one_or_none():
            continue
        profile = User_profiles(
            user_id=user_id,
            display_name=f"Student {user_id}",
            role="normal",
            trust_score=0,
            upload_count=0,
            download_count=0,
            requested_role=None,
            requested_role_status="none",
            account_status="active",
            created_at=_utcnow(),
        )
        db.add(profile)
        created += 1

    await db.commit()
    return {"created": created}
