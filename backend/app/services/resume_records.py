"""ResumeRecord persistence - replaces the old flat-file "resume history"
log (see app/db/models.py's ResumeRecord and app/api/routes/resume.py).

One row per /tailor call. /download looks up the most recent row for a
file_id to know which template + generated filename to use (a single
uploaded CV can be tailored more than once, e.g. for different companies
or templates - the latest tailoring always wins for that file_id).
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.models import ResumeRecord
from app.db.session import engine, session_scope


def ensure_resume_records_schema() -> None:
    """Add job_link / saved-CV columns on existing SQLite DBs."""
    inspector = inspect(engine)
    if "resume_records" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("resume_records")}
    statements: list[str] = []
    if "job_link" not in columns:
        statements.append("ALTER TABLE resume_records ADD COLUMN job_link TEXT NOT NULL DEFAULT ''")
    if "cv_pdf" not in columns:
        statements.append("ALTER TABLE resume_records ADD COLUMN cv_pdf BLOB")
    if "cv_saved" not in columns:
        statements.append("ALTER TABLE resume_records ADD COLUMN cv_saved BOOLEAN NOT NULL DEFAULT 0")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def save_resume_record(
    *,
    file_id: str,
    template_id: int | None,
    candidate_name: str,
    main_stack: str,
    company_name: str,
    generated_filename: str,
    user_id: int | None = None,
    job_link: str = "",
) -> None:
    with session_scope() as session:
        session.add(
            ResumeRecord(
                file_id=file_id,
                template_id=template_id,
                candidate_name=candidate_name,
                main_stack=main_stack,
                company_name=company_name,
                job_link=job_link,
                generated_filename=generated_filename,
                user_id=user_id,
            )
        )


def get_latest_resume_record(file_id: str) -> ResumeRecord | None:
    with session_scope() as session:
        row = (
            session.query(ResumeRecord)
            .filter_by(file_id=file_id)
            .order_by(ResumeRecord.id.desc())
            .first()
        )
        if row is not None:
            session.expunge(row)
        return row


def list_resume_records(limit: int | None = None, user_id: int | None = None) -> list[ResumeRecord]:
    """Most-recent-first list of generated resume metadata.

    Returns every matching row by default (no cap). Pass limit only when a
    caller intentionally wants a truncated window. PDF blobs are deferred so
    large histories stay cheap to list.
    """
    from sqlalchemy.orm import defer

    with session_scope() as session:
        query = session.query(ResumeRecord).options(defer(ResumeRecord.cv_pdf))
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        query = query.order_by(ResumeRecord.id.desc())
        if limit is not None:
            query = query.limit(limit)
        rows = query.all()
        session.expunge_all()
        return rows


def _normalize_job_link_key(raw: str) -> str:
    """Collapse trivial URL variants so duplicate postings map to one row."""
    link = (raw or "").strip()
    if not link:
        return ""
    key = link.rstrip("/")
    if "://" in key:
        scheme, rest = key.split("://", 1)
        key = f"{scheme.lower()}://{rest}"
    return key.lower()


def list_unique_job_links(
    user_id: int | None = None,
    *,
    include_user: bool = False,
) -> list[dict]:
    """Unique non-empty job links, newest first.

    When ``user_id`` is set, only that user's records are considered.
    When omitted, all users are included and links are deduped globally.
    Duplicate links keep the newest row's stack / created_at (and user info
    when ``include_user`` is True).
    """
    from sqlalchemy.orm import defer

    from app.db.models import User

    with session_scope() as session:
        query = session.query(ResumeRecord).options(defer(ResumeRecord.cv_pdf))
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        records = query.order_by(ResumeRecord.id.desc()).all()

        users_by_id: dict[int, User] = {}
        if include_user:
            user_ids = {r.user_id for r in records if r.user_id is not None}
            if user_ids:
                for user in session.query(User).filter(User.id.in_(user_ids)).all():
                    users_by_id[user.id] = user

        seen: set[str] = set()
        items: list[dict] = []
        for record in records:
            link = (getattr(record, "job_link", "") or "").strip()
            key = _normalize_job_link_key(link)
            if not key or key in seen:
                continue
            seen.add(key)
            item: dict = {
                "job_link": link,
                "main_stack": record.main_stack or "",
                "created_at": record.created_at.isoformat() if record.created_at else "",
            }
            if include_user:
                owner = users_by_id.get(record.user_id) if record.user_id is not None else None
                item["user_id"] = record.user_id
                item["user_name"] = owner.name if owner is not None else ""
                item["user_email"] = owner.email if owner is not None else ""
            items.append(item)
        return items


def save_downloaded_cv(file_id: str, pdf_bytes: bytes) -> None:
    """Persist the rendered PDF on the latest ResumeRecord for this file_id."""
    with session_scope() as session:
        row = (
            session.query(ResumeRecord)
            .filter_by(file_id=file_id)
            .order_by(ResumeRecord.id.desc())
            .first()
        )
        if row is None:
            return
        row.cv_pdf = pdf_bytes
        row.cv_saved = True


def get_resume_record(record_id: int) -> ResumeRecord | None:
    with session_scope() as session:
        row = session.get(ResumeRecord, record_id)
        if row is None:
            return None
        _ = row.cv_pdf
        session.expunge(row)
        return row
