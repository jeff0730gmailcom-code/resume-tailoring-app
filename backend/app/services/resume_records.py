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


def list_resume_records(limit: int = 200, user_id: int | None = None) -> list[ResumeRecord]:
    """Most-recent-first list of generated resume metadata."""
    with session_scope() as session:
        query = session.query(ResumeRecord)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        rows = query.order_by(ResumeRecord.id.desc()).limit(limit).all()
        session.expunge_all()
        return rows


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
