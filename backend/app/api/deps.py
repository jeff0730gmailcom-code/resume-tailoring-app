"""FastAPI dependencies for the signed-in user."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.models.schemas import UserPublic
from app.services.auth_service import AuthError, get_user_by_id, user_id_from_token, user_can_use_app


def _to_public(user) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_approved=bool(user.is_approved) or user.role == "admin",
        is_active=bool(user.is_active),
    )


def get_current_user(authorization: str | None = Header(default=None)) -> UserPublic:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
    try:
        user_id = user_id_from_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has been blocked by an administrator.",
        )
    return _to_public(user)


def get_approved_user(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user_can_use_app(user.role, user.is_approved):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An administrator must allow your account before you can use this app.",
        )
    return user


def get_admin_user(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")
    return user
