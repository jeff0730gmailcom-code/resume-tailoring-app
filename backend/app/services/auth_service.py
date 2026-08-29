"""Password hashing, JWT sessions, and Google ID-token verification."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings
from app.db.models import User
from app.db.session import session_scope


class AuthError(Exception):
    """Raised for invalid credentials or Google tokens."""


FOUNDING_ADMIN_NAME = "steve jeff"


def is_founding_admin_name(name: str) -> bool:
    return name.strip().lower() == FOUNDING_ADMIN_NAME


def user_can_use_app(role: str, is_approved: bool) -> bool:
    return role == "admin" or bool(is_approved)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    secret = settings.jwt_secret.strip()
    if not secret:
        raise AuthError("JWT_SECRET is not set in backend/.env.")
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "email": user.email, "exp": expire}
    return jwt.encode(payload, secret, algorithm="HS256")


def user_id_from_token(token: str) -> int:
    secret = settings.jwt_secret.strip()
    if not secret:
        raise AuthError("JWT_SECRET is not set in backend/.env.")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AuthError("Please sign in again.") from exc
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("Please sign in again.") from exc


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _looks_like_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1] and " " not in email


def register_user(name: str, email: str, password: str) -> User:
    name = name.strip()
    email = normalize_email(email)
    if not name:
        raise AuthError("Name is required.")
    if not _looks_like_email(email):
        raise AuthError("Enter a valid email address.")
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")

    with session_scope() as session:
        existing = session.query(User).filter_by(email=email).first()
        if existing is not None:
            raise AuthError("An account with this email already exists.")
        is_first = session.query(User).count() == 0
        make_admin = is_first or is_founding_admin_name(name)
        user = User(
            email=email,
            name=name,
            password_hash=hash_password(password),
            role="admin" if make_admin else "user",
            is_approved=make_admin,
            is_active=True,
            email_verified=False,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        session.expunge(user)
        return user


def authenticate_user(email: str, password: str) -> User:
    email = normalize_email(email)
    with session_scope() as session:
        user = session.query(User).filter_by(email=email).first()
        if user is None:
            raise AuthError("Invalid email or password.")
        if not user.is_active:
            raise AuthError("This account has been blocked by an administrator.")
        if not user.password_hash:
            raise AuthError("This email uses Google Sign-In. Continue with Google.")
        if not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password.")
        if is_founding_admin_name(user.name):
            user.role = "admin"
            user.is_approved = True
        session.expunge(user)
        return user


def _google_profile(credential: str) -> dict[str, str]:
    client_id = settings.google_client_id.strip()
    if not client_id:
        raise AuthError("Google Sign-In is not configured.")
    try:
        info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=10,
        )
    except Exception as exc:  # noqa: BLE001 - google-auth raises several types
        raise AuthError("Google sign-in failed. Try again.") from exc
    issuer = info.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise AuthError("Google sign-in failed. Try again.")
    email = normalize_email(str(info.get("email") or ""))
    if not email or not info.get("email_verified"):
        raise AuthError("Google did not provide a verified email.")
    return {
        "email": email,
        "name": str(info.get("name") or email.split("@")[0]).strip(),
        "google_id": str(info["sub"]),
    }


def authenticate_google(credential: str) -> User:
    profile = _google_profile(credential)
    with session_scope() as session:
        user = session.query(User).filter_by(google_id=profile["google_id"]).first()
        if user is None:
            user = session.query(User).filter_by(email=profile["email"]).first()
        if user is None:
            is_first = session.query(User).count() == 0
            make_admin = is_first or is_founding_admin_name(profile["name"])
            user = User(
                email=profile["email"],
                name=profile["name"],
                google_id=profile["google_id"],
                role="admin" if make_admin else "user",
                is_approved=make_admin,
                is_active=True,
                email_verified=True,
            )
            session.add(user)
            session.flush()
        else:
            if not user.is_active:
                raise AuthError("This account has been blocked by an administrator.")
            if user.google_id is None:
                user.google_id = profile["google_id"]
            if not user.name:
                user.name = profile["name"]
            if is_founding_admin_name(user.name) or is_founding_admin_name(profile["name"]):
                user.role = "admin"
                user.is_approved = True
            user.email_verified = True
        session.refresh(user)
        session.expunge(user)
        return user


def get_user_by_id(user_id: int) -> User | None:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        session.expunge(user)
        return user
