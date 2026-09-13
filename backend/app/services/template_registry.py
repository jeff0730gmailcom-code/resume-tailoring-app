"""Resume template registry: built-in Jinja layouts + per-user PDF/DOCX uploads.

Built-in templates (mateo, marek, nemanja, quang) live under
app/templates/resumes/<slug>/ and are owned by the founding admin.
Every other user only sees and uses templates they uploaded themselves.
"""
from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.models import ResumeTemplate, User
from app.db.session import engine, session_scope
from app.services.auth_service import is_founding_admin_name

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "resumes"
_THUMBNAIL_DIRNAME = "template_previews"
_USER_TEMPLATES_DIRNAME = "user_templates"

# Built-in Jinja layouts assigned to the founding admin (Steve Jeff).
_BUILTIN_SLUGS: frozenset[str] = frozenset({"mateo", "marek", "nemanja", "quang"})
_DEFAULT_BUILTIN_SLUG = "mateo"

_TEMPLATE_META: dict[str, tuple[str, str]] = {
    "marek": ("Marek", "Traditional black & white layout with a serif font and bold inline keyword emphasis."),
    "mateo": ("Mateo", "Large two-line name with top-right contact icons and a colored job-title line."),
    "nemanja": ("Nemanja", "Fully centered header and contact row, with underlined all-caps section headings."),
    "quang": ("Quang Dang", "Centered teal header and contact row, with underlined teal section headings."),
}

_ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx"}
_NAME_FROM_FILENAME_RE = re.compile(r"[_\-]+")


def ensure_templates_schema() -> None:
    """Add ownership columns to existing SQLite DBs. create_all does not alter columns."""
    inspector = inspect(engine)
    if "resume_templates" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("resume_templates")}
    statements: list[str] = []
    if "user_id" not in columns:
        statements.append("ALTER TABLE resume_templates ADD COLUMN user_id INTEGER")
    if "is_builtin" not in columns:
        statements.append("ALTER TABLE resume_templates ADD COLUMN is_builtin BOOLEAN NOT NULL DEFAULT 0")
    if "source_path" not in columns:
        statements.append("ALTER TABLE resume_templates ADD COLUMN source_path VARCHAR(512) NOT NULL DEFAULT ''")
    if "is_default" not in columns:
        statements.append("ALTER TABLE resume_templates ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT 0")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _thumbnail_dir(static_dir: Path) -> Path:
    path = static_dir / _THUMBNAIL_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_templates_root() -> Path:
    path = settings.database_path.parent / _USER_TEMPLATES_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_thumbnail(slug: str, reference_pdf: Path, static_dir: Path, *, force: bool = False) -> str:
    relative_path = f"{_THUMBNAIL_DIRNAME}/{slug}.png"
    thumbnail_path = static_dir / relative_path
    if thumbnail_path.exists() and not force:
        return relative_path

    _thumbnail_dir(static_dir)
    doc = fitz.open(str(reference_pdf))
    try:
        page = doc[0]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pixmap.save(str(thumbnail_path))
    finally:
        doc.close()
    return relative_path


def _founding_admin_id(session) -> int | None:
    for user in session.query(User).all():
        if is_founding_admin_name(user.name) or user.role == "admin":
            if is_founding_admin_name(user.name):
                return user.id
    admin = session.query(User).filter_by(role="admin").order_by(User.id.asc()).first()
    return admin.id if admin is not None else None


def seed_templates_from_disk(static_dir: Path) -> None:
    """Upsert the four admin-owned built-in templates; deactivate other disk folders."""
    if not _TEMPLATES_DIR.exists():
        logger.warning("Template directory %s does not exist - no templates seeded", _TEMPLATES_DIR)
        return

    with session_scope() as session:
        admin_id = _founding_admin_id(session)

        for template_dir in sorted(_TEMPLATES_DIR.iterdir()):
            if not template_dir.is_dir() or template_dir.name.startswith("_"):
                continue
            slug = template_dir.name
            html_path = template_dir / "template.html.jinja2"
            reference_pdf = template_dir / "reference.pdf"
            existing = session.query(ResumeTemplate).filter_by(slug=slug).one_or_none()

            if slug not in _BUILTIN_SLUGS:
                if existing is not None:
                    existing.is_active = False
                continue

            if not html_path.exists() or not reference_pdf.exists():
                logger.warning("Skipping built-in template %r - missing template.html.jinja2 or reference.pdf", slug)
                continue

            name, description = _TEMPLATE_META.get(slug, (slug.title(), ""))
            thumbnail_path = _ensure_thumbnail(slug, reference_pdf, static_dir)
            is_default = slug == _DEFAULT_BUILTIN_SLUG

            if existing is None:
                session.add(
                    ResumeTemplate(
                        slug=slug,
                        name=name,
                        description=description,
                        thumbnail_path=thumbnail_path,
                        is_active=True,
                        user_id=admin_id,
                        is_builtin=True,
                        source_path="",
                        is_default=is_default,
                    )
                )
            else:
                existing.name = name
                existing.description = description
                existing.thumbnail_path = thumbnail_path
                existing.is_active = True
                existing.is_builtin = True
                existing.source_path = ""
                if admin_id is not None:
                    existing.user_id = admin_id
                if is_default:
                    existing.is_default = True

        if admin_id is not None:
            defaults = (
                session.query(ResumeTemplate)
                .filter_by(user_id=admin_id, is_active=True, is_default=True)
                .all()
            )
            if len(defaults) > 1:
                for row in defaults:
                    row.is_default = row.slug == _DEFAULT_BUILTIN_SLUG
            elif not defaults:
                mateo = session.query(ResumeTemplate).filter_by(slug=_DEFAULT_BUILTIN_SLUG).one_or_none()
                if mateo is not None:
                    mateo.is_default = True
                    mateo.user_id = admin_id


def assign_builtin_templates_to_admin(user_id: int) -> None:
    """Call after founding admin is ensured so built-ins are never ownerless."""
    with session_scope() as session:
        for slug in _BUILTIN_SLUGS:
            row = session.query(ResumeTemplate).filter_by(slug=slug).one_or_none()
            if row is None:
                continue
            row.user_id = user_id
            row.is_builtin = True
            row.is_active = True
            if slug == _DEFAULT_BUILTIN_SLUG:
                row.is_default = True


def _to_info_fields(row: ResumeTemplate) -> dict:
    return {
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "thumbnail_path": row.thumbnail_path,
        "is_builtin": bool(row.is_builtin),
        "is_default": bool(row.is_default),
        "user_id": row.user_id,
    }


def list_templates_for_user(user_id: int) -> list[ResumeTemplate]:
    """Active templates owned by this user only."""
    with session_scope() as session:
        rows = (
            session.query(ResumeTemplate)
            .filter_by(user_id=user_id, is_active=True)
            .order_by(ResumeTemplate.is_default.desc(), ResumeTemplate.slug)
            .all()
        )
        session.expunge_all()
        return rows


def list_templates_for_users(user_ids: list[int]) -> dict[int, list[ResumeTemplate]]:
    if not user_ids:
        return {}
    with session_scope() as session:
        rows = (
            session.query(ResumeTemplate)
            .filter(ResumeTemplate.user_id.in_(user_ids), ResumeTemplate.is_active.is_(True))
            .order_by(ResumeTemplate.slug)
            .all()
        )
        by_user: dict[int, list[ResumeTemplate]] = {uid: [] for uid in user_ids}
        for row in rows:
            if row.user_id is None:
                continue
            session.expunge(row)
            by_user.setdefault(row.user_id, []).append(row)
        return by_user


def get_template(slug: str) -> ResumeTemplate | None:
    with session_scope() as session:
        row = session.query(ResumeTemplate).filter_by(slug=slug, is_active=True).one_or_none()
        if row is not None:
            session.expunge(row)
        return row


def get_template_for_user(slug: str, user_id: int) -> ResumeTemplate | None:
    with session_scope() as session:
        row = (
            session.query(ResumeTemplate)
            .filter_by(slug=slug, user_id=user_id, is_active=True)
            .one_or_none()
        )
        if row is not None:
            session.expunge(row)
        return row


def get_template_by_id(template_id: int) -> ResumeTemplate | None:
    with session_scope() as session:
        row = session.query(ResumeTemplate).filter_by(id=template_id).one_or_none()
        if row is not None:
            session.expunge(row)
        return row


def _display_name_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip() or "My template"
    cleaned = _NAME_FROM_FILENAME_RE.sub(" ", stem).strip()
    return cleaned[:120] if cleaned else "My template"


async def create_uploaded_template(
    *,
    user_id: int,
    original_filename: str,
    content: bytes,
    static_dir: Path,
) -> ResumeTemplate:
    """Store a user-uploaded PDF/DOCX sample CV as a private template."""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("Template upload must be a PDF or DOCX file.")
    if not content:
        raise ValueError("Uploaded template file is empty.")

    slug = f"u{user_id}-{uuid.uuid4().hex[:10]}"
    dest_dir = user_templates_root() / str(user_id) / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_path = dest_dir / f"source{suffix}"
    source_path.write_bytes(content)

    working_docx = dest_dir / "working.docx"
    preview_pdf = dest_dir / "preview.pdf"

    from app.services.docx_to_pdf import convert_docx_to_pdf, convert_to_docx

    if suffix == ".docx":
        shutil.copy2(source_path, working_docx)
        ok = await convert_docx_to_pdf(working_docx, preview_pdf)
        if not ok:
            # Thumbnail fallback: leave preview missing and use a blank page later.
            preview_pdf = None
    else:
        shutil.copy2(source_path, preview_pdf)
        ok = await convert_to_docx(source_path, working_docx)
        if not ok:
            working_docx.unlink(missing_ok=True)

    if preview_pdf is not None and preview_pdf.exists():
        thumbnail_path = _ensure_thumbnail(slug, preview_pdf, static_dir, force=True)
    else:
        # Minimal placeholder so the gallery still loads.
        thumbnail_path = f"{_THUMBNAIL_DIRNAME}/{slug}.png"
        thumb = static_dir / thumbnail_path
        _thumbnail_dir(static_dir)
        if not thumb.exists():
            doc = fitz.open()
            try:
                page = doc.new_page(width=595, height=842)
                page.insert_text((72, 72), "Template preview unavailable", fontsize=14)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                pix.save(str(thumb))
            finally:
                doc.close()

    name = _display_name_from_filename(original_filename)
    with session_scope() as session:
        has_any = (
            session.query(ResumeTemplate)
            .filter_by(user_id=user_id, is_active=True)
            .count()
        )
        row = ResumeTemplate(
            slug=slug,
            name=name,
            description="Uploaded sample CV used as your private resume template.",
            thumbnail_path=thumbnail_path,
            is_active=True,
            user_id=user_id,
            is_builtin=False,
            source_path=str(source_path.resolve()),
            is_default=has_any == 0,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        session.expunge(row)
        return row


def set_default_template(*, user_id: int, slug: str) -> ResumeTemplate:
    with session_scope() as session:
        target = (
            session.query(ResumeTemplate)
            .filter_by(slug=slug, user_id=user_id, is_active=True)
            .one_or_none()
        )
        if target is None:
            raise ValueError("Template not found.")
        for row in session.query(ResumeTemplate).filter_by(user_id=user_id, is_active=True).all():
            row.is_default = row.id == target.id
        session.flush()
        session.refresh(target)
        session.expunge(target)
        return target


def delete_user_template(*, user_id: int, slug: str) -> None:
    with session_scope() as session:
        row = (
            session.query(ResumeTemplate)
            .filter_by(slug=slug, user_id=user_id, is_active=True)
            .one_or_none()
        )
        if row is None:
            raise ValueError("Template not found.")
        if row.is_builtin:
            raise ValueError("Built-in templates cannot be deleted.")
        was_default = bool(row.is_default)
        source = Path(row.source_path) if row.source_path else None
        row.is_active = False
        row.is_default = False
        if was_default:
            replacement = (
                session.query(ResumeTemplate)
                .filter_by(user_id=user_id, is_active=True)
                .order_by(ResumeTemplate.slug)
                .first()
            )
            if replacement is not None:
                replacement.is_default = True
    if source is not None and source.exists():
        shutil.rmtree(source.parent, ignore_errors=True)


def delete_templates_for_user(user_id: int) -> None:
    with session_scope() as session:
        rows = session.query(ResumeTemplate).filter_by(user_id=user_id).all()
        for row in rows:
            if row.source_path:
                path = Path(row.source_path)
                if path.exists():
                    shutil.rmtree(path.parent, ignore_errors=True)
            session.delete(row)


def resolve_working_docx(template: ResumeTemplate) -> Path | None:
    """Return the DOCX used to fill an uploaded template, if available."""
    if template.is_builtin or not template.source_path:
        return None
    source = Path(template.source_path)
    working = source.parent / "working.docx"
    if working.exists():
        return working
    if source.suffix.lower() == ".docx" and source.exists():
        return source
    return None
