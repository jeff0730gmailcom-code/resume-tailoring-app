"""SQLAlchemy ORM models for the two tables this app needs:

- ResumeTemplate: the selectable resume layouts shown in the frontend
  gallery (see app/services/template_registry.py, which seeds these from
  app/templates/resumes/*/ on startup).
- ResumeRecord: one row per generated tailored resume, replacing the old
  flat-file "resume history" log - see app/api/routes/resume.py.

user_id on ResumeRecord is deliberately nullable and unused for now -
authentication is out of scope for this phase, but the column means adding
user accounts later never requires a schema rework, just wiring an actual
user id through.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResumeTemplate(Base):
    __tablename__ = "resume_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Path to the gallery thumbnail, relative to the /static mount (see
    # app/main.py) - e.g. "template_previews/dejan.png". The thumbnail is
    # the real sample CV's own first page (see template_registry.py), not
    # a synthetic re-render.
    thumbnail_path: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    resume_records: Mapped[list["ResumeRecord"]] = relationship(back_populates="template")


class ResumeRecord(Base):
    __tablename__ = "resume_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("resume_templates.id"), nullable=True)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    main_stack: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    generated_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Reserved for future auth - always NULL today, never read/written
    # anywhere yet. See module docstring.
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    template: Mapped["ResumeTemplate | None"] = relationship(back_populates="resume_records")
