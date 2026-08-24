"""ResumeRecord persistence - replaces the old flat-file "resume history"
log (see app/db/models.py's ResumeRecord and app/api/routes/resume.py).

One row per /tailor call. /download looks up the most recent row for a
file_id to know which template + generated filename to use (a single
uploaded CV can be tailored more than once, e.g. for different companies
or templates - the latest tailoring always wins for that file_id).
"""
from __future__ import annotations

from app.db.models import ResumeRecord
from app.db.session import session_scope


def save_resume_record(
    *,
    file_id: str,
    template_id: int | None,
    candidate_name: str,
    main_stack: str,
    company_name: str,
    generated_filename: str,
) -> None:
    with session_scope() as session:
        session.add(
            ResumeRecord(
                file_id=file_id,
                template_id=template_id,
                candidate_name=candidate_name,
                main_stack=main_stack,
                company_name=company_name,
                generated_filename=generated_filename,
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


def list_resume_records(limit: int = 200) -> list[ResumeRecord]:
    """Most-recent-first list of every generated resume's metadata."""
    with session_scope() as session:
        rows = (
            session.query(ResumeRecord)
            .order_by(ResumeRecord.id.desc())
            .limit(limit)
            .all()
        )
        session.expunge_all()
        return rows
