"""Administrator user list, approval, and block/unblock."""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.models import ResumeRecord, User
from app.db.session import engine, session_scope
from app.services.auth_service import AuthError, is_founding_admin_name


def ensure_users_schema() -> None:
    """Add is_approved to existing SQLite DBs. create_all does not alter columns."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_approved" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN is_approved BOOLEAN NOT NULL DEFAULT 1"))


def ensure_founding_admin() -> None:
    """Steve Jeff is always an active, approved administrator."""
    with session_scope() as session:
        for user in session.query(User).all():
            if is_founding_admin_name(user.name):
                user.role = "admin"
                user.is_approved = True
                user.is_active = True


def _iso(value) -> str:
    if value is None:
        return ""
    text_value = value.isoformat() if hasattr(value, "isoformat") else str(value)
    if text_value.endswith("+00:00"):
        return text_value.replace("+00:00", "Z")
    return text_value


def list_users_for_admin() -> list[tuple[User, list[ResumeRecord]]]:
    with session_scope() as session:
        users = session.query(User).order_by(User.id.asc()).all()
        rows: list[tuple[User, list[ResumeRecord]]] = []
        for user in users:
            records = (
                session.query(ResumeRecord)
                .filter_by(user_id=user.id)
                .order_by(ResumeRecord.id.desc())
                .limit(100)
                .all()
            )
            session.expunge(user)
            for record in records:
                session.expunge(record)
            rows.append((user, records))
        return rows


def get_user_with_activity(user_id: int) -> tuple[User, list[ResumeRecord]] | None:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        records = (
            session.query(ResumeRecord)
            .filter_by(user_id=user.id)
            .order_by(ResumeRecord.id.desc())
            .limit(200)
            .all()
        )
        session.expunge(user)
        for record in records:
            session.expunge(record)
        return user, records


def delete_user(*, actor_id: int, user_id: int) -> None:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise AuthError("User not found.")
        if user.id == actor_id:
            raise AuthError("You cannot delete your own account.")
        if is_founding_admin_name(user.name):
            raise AuthError("The house administrator cannot be deleted.")
        if user.role == "admin":
            other_admins = (
                session.query(User)
                .filter(User.role == "admin", User.is_active.is_(True), User.id != user.id)
                .count()
            )
            if other_admins == 0:
                raise AuthError("Cannot delete the only administrator.")
        session.query(ResumeRecord).filter_by(user_id=user.id).delete()
        session.delete(user)


def update_user_access(
    *,
    actor_id: int,
    user_id: int,
    is_approved: bool | None = None,
    is_active: bool | None = None,
) -> User:
    if is_approved is None and is_active is None:
        raise AuthError("Nothing to update.")

    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise AuthError("User not found.")

        if is_active is False:
            if user.id == actor_id:
                raise AuthError("You cannot block your own account.")
            if user.role == "admin":
                other_admins = (
                    session.query(User)
                    .filter(User.role == "admin", User.is_active.is_(True), User.id != user.id)
                    .count()
                )
                if other_admins == 0:
                    raise AuthError("Cannot block the only administrator.")

        if is_approved is not None:
            user.is_approved = is_approved
            if is_approved:
                user.is_active = True
        if is_active is not None:
            user.is_active = is_active

        session.flush()
        session.refresh(user)
        session.expunge(user)
        return user


def activity_iso(record: ResumeRecord) -> str:
    return _iso(record.created_at)


def user_created_iso(user: User) -> str:
    return _iso(user.created_at)
