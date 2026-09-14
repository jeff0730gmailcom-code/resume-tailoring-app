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
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_STATIC_DIR = _BACKEND_DIR / "static"
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
_UPLOADED_JINJA_NAME = "template.html.jinja2"
_UPLOADED_JINJA_SOURCE = _TEMPLATES_DIR / "_uploaded" / _UPLOADED_JINJA_NAME


def install_uploaded_jinja_layout(dest_dir: Path) -> Path:
    """Copy the Mateo/Marek-style Jinja layout into an upload folder."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _UPLOADED_JINJA_NAME
    if not _UPLOADED_JINJA_SOURCE.exists():
        raise FileNotFoundError(f"Missing uploaded-template Jinja source: {_UPLOADED_JINJA_SOURCE}")
    shutil.copy2(_UPLOADED_JINJA_SOURCE, dest)
    return dest


def uploaded_jinja_path(template: ResumeTemplate) -> Path | None:
    """Return the Jinja file for an uploaded template, if present."""
    if not getattr(template, "source_path", None):
        return None
    path = Path(template.source_path).parent / _UPLOADED_JINJA_NAME
    return path if path.exists() else None


def ensure_uploaded_jinja_layout(template: ResumeTemplate) -> Path | None:
    """Install the shared Jinja layout next to an upload if missing."""
    if not getattr(template, "source_path", None):
        return None
    dest_dir = Path(template.source_path).parent
    if not dest_dir.exists():
        return None
    existing = dest_dir / _UPLOADED_JINJA_NAME
    if existing.exists():
        return existing
    try:
        return install_uploaded_jinja_layout(dest_dir)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Could not install Jinja layout for upload %s",
            getattr(template, "slug", "?"),
            exc_info=True,
        )
        return None


def repair_uploaded_jinja_layouts() -> int:
    """Ensure every active upload has the Mateo-style Jinja template file."""
    repaired = 0
    with session_scope() as session:
        rows = (
            session.query(ResumeTemplate)
            .filter_by(is_builtin=False, is_active=True)
            .all()
        )
        for row in rows:
            if not row.source_path:
                continue
            dest_dir = Path(row.source_path).parent
            if not dest_dir.exists():
                continue
            target = dest_dir / _UPLOADED_JINJA_NAME
            if target.exists():
                row.layout_slug = "uploaded"
                continue
            try:
                install_uploaded_jinja_layout(dest_dir)
                row.layout_slug = "uploaded"
                repaired += 1
            except Exception:  # noqa: BLE001
                logger.warning("Failed installing Jinja for %s", row.slug, exc_info=True)
    return repaired


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
    if "layout_slug" not in columns:
        statements.append("ALTER TABLE resume_templates ADD COLUMN layout_slug VARCHAR(64) NOT NULL DEFAULT ''")
    if "is_default" not in columns:
        statements.append("ALTER TABLE resume_templates ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT 0")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def static_dir() -> Path:
    """Gallery thumbnails live under backend/static (mounted at /static)."""
    path = _DEFAULT_STATIC_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _thumbnail_dir(static_dir_path: Path) -> Path:
    path = static_dir_path / _THUMBNAIL_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_templates_root() -> Path:
    path = settings.database_path.parent / _USER_TEMPLATES_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_placeholder_thumbnail(
    slug: str,
    static_dir_path: Path,
    message: str = "Template preview unavailable",
) -> str:
    relative_path = f"{_THUMBNAIL_DIRNAME}/{slug}.png"
    thumb = static_dir_path / relative_path
    _thumbnail_dir(static_dir_path)
    doc = fitz.open()
    try:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), message[:80], fontsize=14)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(str(thumb))
    finally:
        doc.close()
    return relative_path


def _ensure_thumbnail(slug: str, reference_pdf: Path, static_dir_path: Path, *, force: bool = False) -> str:
    relative_path = f"{_THUMBNAIL_DIRNAME}/{slug}.png"
    thumbnail_path = static_dir_path / relative_path
    if thumbnail_path.exists() and not force:
        return relative_path

    _thumbnail_dir(static_dir_path)
    try:
        doc = fitz.open(str(reference_pdf))
        try:
            page = doc[0]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            pixmap.save(str(thumbnail_path))
        finally:
            doc.close()
        return relative_path
    except Exception:  # noqa: BLE001
        logger.warning("Could not rasterize thumbnail for %s from %s", slug, reference_pdf, exc_info=True)
        return _write_placeholder_thumbnail(slug, static_dir_path)


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
                        layout_slug=slug,
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
                existing.layout_slug = slug
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


def list_jinja_layout_slugs() -> list[str]:
    """All on-disk Jinja resume layouts (including inactive gallery ones like dejan)."""
    if not _TEMPLATES_DIR.exists():
        return []
    slugs: list[str] = []
    for folder in sorted(_TEMPLATES_DIR.iterdir()):
        if folder.is_dir() and not folder.name.startswith("_") and (folder / "template.html.jinja2").exists():
            slugs.append(folder.name)
    return slugs


def detect_layout_slug(*hints: str) -> str:
    """Match hints only to active built-in gallery layouts (mateo/marek/nemanja/quang).

    Never matches inactive on-disk layouts such as dejan/aleksandra — those must
    not hijack a user upload that happens to be named \"Dejan Pavlovic.pdf\".
    Returns '' when nothing matches.
    """
    haystack = " ".join(h for h in hints if h).lower()
    if not haystack:
        return ""
    for slug in sorted(_BUILTIN_SLUGS, key=len, reverse=True):
        if slug.lower() in haystack:
            return slug
    return ""


async def create_uploaded_template(
    *,
    user_id: int,
    original_filename: str,
    content: bytes,
    static_dir_path: Path | None = None,
) -> ResumeTemplate:
    """Store a user-uploaded PDF/DOCX sample as a private template.

    Files land under backend/data/user_templates/<user_id>/<slug>/:
      source.pdf|docx           — original upload (gallery thumbnail source)
      template.html.jinja2      — Mateo/Marek-style Jinja layout for PDF output
      preview.pdf               — thumbnail source
    Thumbnail PNG: backend/static/template_previews/<slug>.png

    Tailored resumes use Jinja + Playwright (same engine as Mateo/Marek).
    """
    static_dir_path = static_dir_path or static_dir()
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

    preview_pdf = dest_dir / "preview.pdf"
    name = _display_name_from_filename(original_filename)
    install_uploaded_jinja_layout(dest_dir)

    from app.services.docx_to_pdf import convert_docx_to_pdf

    preview_ok = False
    if suffix == ".docx":
        preview_ok = await convert_docx_to_pdf(source_path, preview_pdf)
        if not preview_ok:
            logger.warning("DOCX→PDF failed for uploaded template %s; using placeholder thumbnail", slug)
    else:
        shutil.copy2(source_path, preview_pdf)
        preview_ok = preview_pdf.exists() and preview_pdf.stat().st_size > 0

    if preview_ok and preview_pdf.exists():
        thumbnail_path = _ensure_thumbnail(slug, preview_pdf, static_dir_path, force=True)
    else:
        thumbnail_path = _write_placeholder_thumbnail(
            slug,
            static_dir_path,
            "Preview unavailable — re-upload as PDF if this persists",
        )

    served = static_dir_path / thumbnail_path
    if not served.exists():
        thumbnail_path = _write_placeholder_thumbnail(slug, static_dir_path)

    with session_scope() as session:
        has_any = (
            session.query(ResumeTemplate)
            .filter_by(user_id=user_id, is_active=True)
            .count()
        )
        row = ResumeTemplate(
            slug=slug,
            name=name,
            description="Uploaded sample — tailored with the same Jinja/Playwright engine as Mateo/Marek.",
            thumbnail_path=thumbnail_path,
            is_active=True,
            user_id=user_id,
            is_builtin=False,
            source_path=str(source_path.resolve()),
            layout_slug="uploaded",
            is_default=has_any == 0,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        session.expunge(row)
        return row


def repair_uploaded_template_thumbnails(static_dir_path: Path | None = None) -> int:
    """Rebuild missing thumbnails for uploaded templates (wrong path / failed convert).

    Also clears layout_slug values that pointed uploads at inactive Jinja layouts
    (e.g. Dejan upload → dejan), which caused the wrong template to render.
    """
    static_dir_path = static_dir_path or static_dir()
    repaired = 0
    with session_scope() as session:
        rows = (
            session.query(ResumeTemplate)
            .filter_by(is_builtin=False, is_active=True)
            .all()
        )
        for row in rows:
            stored = (getattr(row, "layout_slug", None) or "").strip()
            if stored and stored not in _BUILTIN_SLUGS and stored != "uploaded":
                # Clear hijacks like layout_slug='dejan' on an upload named Dejan.
                row.layout_slug = "uploaded" if row.source_path else ""
                repaired += 1
            elif stored in _BUILTIN_SLUGS and row.source_path:
                row.layout_slug = "uploaded"
                repaired += 1
            elif row.source_path and stored != "uploaded":
                row.layout_slug = "uploaded"
            thumb = static_dir_path / row.thumbnail_path
            if thumb.exists() and thumb.stat().st_size > 0:
                continue
            source = Path(row.source_path) if row.source_path else None
            preview = source.parent / "preview.pdf" if source else None
            if preview is not None and preview.exists():
                row.thumbnail_path = _ensure_thumbnail(row.slug, preview, static_dir_path, force=True)
                repaired += 1
                continue
            if source is not None and source.exists() and source.suffix.lower() == ".pdf":
                row.thumbnail_path = _ensure_thumbnail(row.slug, source, static_dir_path, force=True)
                repaired += 1
                continue
            row.thumbnail_path = _write_placeholder_thumbnail(row.slug, static_dir_path)
            repaired += 1
    return repaired


def repair_uploaded_working_docx() -> int:
    """Ensure every active uploaded template has a fillable working.docx.

    Uses Word COM when possible, otherwise PyMuPDF. Safe to call from sync
    startup code (no nested event loop).
    """
    from app.services.docx_to_pdf import _convert_to_docx_sync, _pdf_to_docx_pymupdf

    repaired = 0
    with session_scope() as session:
        rows = (
            session.query(ResumeTemplate)
            .filter_by(is_builtin=False, is_active=True)
            .all()
        )
        targets: list[Path] = []
        for row in rows:
            if not row.source_path:
                continue
            source = Path(row.source_path)
            if not source.exists():
                continue
            working = source.parent / "working.docx"
            if working.exists() and working.stat().st_size > 0:
                continue
            targets.append(source)

    for source in targets:
        working = source.parent / "working.docx"
        ok = False
        if source.suffix.lower() == ".docx":
            try:
                shutil.copy2(source, working)
                ok = working.exists() and working.stat().st_size > 0
            except Exception:  # noqa: BLE001
                logger.warning("Could not copy DOCX template %s", source, exc_info=True)
        else:
            ok = _convert_to_docx_sync(source, working)
            if not ok and source.suffix.lower() == ".pdf":
                working.unlink(missing_ok=True)
                ok = _pdf_to_docx_pymupdf(source, working)
        if ok:
            repaired += 1
            logger.info("Repaired working.docx for uploaded template %s", source.parent.name)
        else:
            logger.warning("Could not repair working.docx for %s", source)
    return repaired


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


def template_has_jinja_layout(template: ResumeTemplate) -> bool:
    """True when this template should render via Jinja2 + Playwright.

    Built-in gallery layouts and uploaded samples (with template.html.jinja2)
    both use the Mateo/Marek engine.
    """
    slug = (template.slug or "").strip()
    if slug in _BUILTIN_SLUGS:
        return True
    if slug and (_TEMPLATES_DIR / slug / "template.html.jinja2").exists():
        return True
    if uploaded_jinja_path(template) is not None:
        return True
    if getattr(template, "source_path", None):
        # Uploads always get a Jinja file; install on demand if missing.
        return ensure_uploaded_jinja_layout(template) is not None
    return bool(getattr(template, "is_builtin", False)) and not getattr(template, "source_path", "")


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
