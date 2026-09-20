"""Administrator endpoints: members, approval, and block."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_admin_user
from app.models.schemas import (
    AdminUserActivity,
    AdminUserRow,
    AdminUserUpdate,
    JobLinkHistoryItem,
    ResumeTemplateInfo,
    UserPublic,
)
from app.services.admin_users import (
    activity_iso,
    delete_user,
    get_user_with_activity,
    list_users_for_admin,
    update_user_access,
    user_created_iso,
)
from app.services.auth_service import AuthError
from app.services.resume_records import list_unique_job_links
from app.services.template_registry import list_templates_for_users

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _template_info(template) -> ResumeTemplateInfo:
    return ResumeTemplateInfo(
        slug=template.slug,
        name=template.name,
        description=template.description,
        thumbnail_url=f"/static/{template.thumbnail_path}",
        is_builtin=bool(getattr(template, "is_builtin", False)),
        is_default=bool(getattr(template, "is_default", False)),
    )


def _row(user, records, templates=None, resume_count: int | None = None) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_approved=bool(user.is_approved) or user.role == "admin",
        is_active=bool(user.is_active),
        created_at=user_created_iso(user),
        resume_count=len(records) if resume_count is None else resume_count,
        activity=[
            AdminUserActivity(
                id=record.id,
                candidate_name=record.candidate_name,
                main_stack=record.main_stack,
                company_name=record.company_name,
                job_link=getattr(record, "job_link", "") or "",
                generated_filename=record.generated_filename,
                created_at=activity_iso(record),
                cv_saved=bool(getattr(record, "cv_saved", False)),
            )
            for record in records
        ],
        templates=[_template_info(t) for t in (templates or [])],
    )


@router.get("/users", response_model=list[AdminUserRow])
async def admin_list_users(_admin: UserPublic = Depends(get_admin_user)) -> list[AdminUserRow]:
    pairs = list_users_for_admin()
    templates_by_user = list_templates_for_users([user.id for user, _count, _records in pairs])
    return [
        _row(user, records, templates_by_user.get(user.id, []), resume_count=count)
        for user, count, records in pairs
    ]


@router.patch("/users/{user_id}", response_model=AdminUserRow)
async def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin: UserPublic = Depends(get_admin_user),
) -> AdminUserRow:
    try:
        update_user_access(
            actor_id=admin.id,
            user_id=user_id,
            is_approved=payload.is_approved,
            is_active=payload.is_active,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    for user, count, records in list_users_for_admin():
        if user.id == user_id:
            templates = list_templates_for_users([user_id]).get(user_id, [])
            return _row(user, records, templates, resume_count=count)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


@router.get("/users/{user_id}", response_model=AdminUserRow)
async def admin_get_user(user_id: int, _admin: UserPublic = Depends(get_admin_user)) -> AdminUserRow:
    loaded = get_user_with_activity(user_id)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user, records = loaded
    templates = list_templates_for_users([user_id]).get(user_id, [])
    return _row(user, records, templates)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(user_id: int, admin: UserPublic = Depends(get_admin_user)) -> None:
    try:
        delete_user(actor_id=admin.id, user_id=user_id)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/job-links", response_model=list[JobLinkHistoryItem])
async def admin_all_job_links(_admin: UserPublic = Depends(get_admin_user)) -> list[JobLinkHistoryItem]:
    """All users' unique job links (duplicates collapsed globally), newest first."""
    return [JobLinkHistoryItem(**item) for item in list_unique_job_links(include_user=True)]


@router.get("/users/{user_id}/job-links", response_model=list[JobLinkHistoryItem])
async def admin_user_job_links(
    user_id: int,
    _admin: UserPublic = Depends(get_admin_user),
) -> list[JobLinkHistoryItem]:
    """One member's unique job links for administrators."""
    loaded = get_user_with_activity(user_id)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user, _records = loaded
    items = list_unique_job_links(user_id, include_user=True)
    # Ensure user fields are filled even when include_user lookup is sparse.
    return [
        JobLinkHistoryItem(
            **{
                **item,
                "user_id": user.id,
                "user_name": item.get("user_name") or user.name,
                "user_email": item.get("user_email") or user.email,
            }
        )
        for item in items
    ]
