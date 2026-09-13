"""SQLAlchemy ORM models for the tables this app needs:

- ResumeTemplate: selectable resume layouts. Built-in Jinja templates are
  owned by the founding admin; each user may also upload their own
  PDF/DOCX sample CVs as private templates.
- ResumeRecord: one row per generated tailored resume.
- User: auth accounts (see app/api/routes/auth.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
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
    # Path to the gallery thumbnail, relative to the /static mount.
    thumbnail_path: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Owner of this template. Built-ins are assigned to the founding admin;
    # uploaded templates belong to the uploading user. Users only list/use
    # their own rows.
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # True for on-disk Jinja layouts under app/templates/resumes/<slug>/.
    is_builtin: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Absolute or backend-relative path to the uploaded PDF/DOCX source.
    # Empty for built-in Jinja templates.
    source_path: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # When an upload cannot be filled as DOCX, render with this on-disk Jinja
    # layout (e.g. "dejan"). Empty for built-ins (they use their own slug).
    layout_slug: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # One default template per user; auto-selected in the gallery.
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)

    resume_records: Mapped[list["ResumeRecord"]] = relationship(back_populates="template")
    owner: Mapped["User | None"] = relationship(back_populates="templates")


class ResumeRecord(Base):
    __tablename__ = "resume_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("resume_templates.id"), nullable=True)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    main_stack: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_link: Mapped[str] = mapped_column(Text, default="", nullable=False)
    generated_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    cv_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    cv_saved: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    template: Mapped["ResumeTemplate | None"] = relationship(back_populates="resume_records")
    user: Mapped["User | None"] = relationship(back_populates="resume_records")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_approved: Mapped[bool] = mapped_column(default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    resume_records: Mapped[list["ResumeRecord"]] = relationship(back_populates="user")
    templates: Mapped[list["ResumeTemplate"]] = relationship(back_populates="owner")
