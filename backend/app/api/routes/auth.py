"""Auth endpoints: register, email login, Google Sign-In, current user."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.schemas import (
    AuthConfigResponse,
    AuthResponse,
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    UserPublic,
)
from app.services.auth_service import (
    AuthError,
    authenticate_google,
    authenticate_user,
    create_access_token,
    register_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_response(user) -> AuthResponse:
    try:
        token = create_access_token(user)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return AuthResponse(
        token=token,
        user=UserPublic(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_approved=bool(user.is_approved) or user.role == "admin",
            is_active=bool(user.is_active),
        ),
    )


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(google_client_id=settings.google_client_id.strip())


@router.post("/register", response_model=AuthResponse)
async def register(payload: RegisterRequest) -> AuthResponse:
    try:
        user = register_user(payload.name, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    try:
        user = authenticate_user(payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _auth_response(user)


@router.post("/google", response_model=AuthResponse)
async def google_login(payload: GoogleAuthRequest) -> AuthResponse:
    try:
        user = authenticate_google(payload.credential)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _auth_response(user)


@router.get("/me", response_model=UserPublic)
async def me(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return user
