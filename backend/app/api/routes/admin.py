"""Administrator endpoints: members, approval, and block."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_admin_user
from app.models.schemas import AdminUserActivity, AdminUserRow, AdminUserUpdate, UserPublic
from app.services.admin_users import (
    activity_iso,
    delete_user,
    get_user_with_activity,
    list_users_for_admin,
    update_user_access,
    user_created_iso,
)
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _row(user, records) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_approved=bool(user.is_approved) or user.role == "admin",
        is_active=bool(user.is_active),
        created_at=user_created_iso(user),
        resume_count=len(records),
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
    )


@router.get("/users", response_model=list[AdminUserRow])
async def admin_list_users(_admin: UserPublic = Depends(get_admin_user)) -> list[AdminUserRow]:
    return [_row(user, records) for user, records in list_users_for_admin()]


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
    for user, records in list_users_for_admin():
        if user.id == user_id:
            return _row(user, records)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


@router.get("/users/{user_id}", response_model=AdminUserRow)
async def admin_get_user(user_id: int, _admin: UserPublic = Depends(get_admin_user)) -> AdminUserRow:
    loaded = get_user_with_activity(user_id)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user, records = loaded
    return _row(user, records)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(user_id: int, admin: UserPublic = Depends(get_admin_user)) -> None:
    try:
        delete_user(actor_id=admin.id, user_id=user_id)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
