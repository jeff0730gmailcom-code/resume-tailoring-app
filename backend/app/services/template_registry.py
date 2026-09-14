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
    """Pick a starter Jinja for a new upload from its filename/display name.

    Only active gallery builtins (mateo/marek/nemanja/quang) — never inactive
    coded ``dejan`` (that stole black/white Dejan samples). The matched layout
    is COPIED into the upload folder as that template's own Jinja file;
    rendering always uses the per-upload file, not the gallery path.
    """
    raw = " ".join(h for h in hints if h)
    if not raw:
        return ""
    haystack = _NAME_FROM_FILENAME_RE.sub(" ", raw).lower()
    for slug in sorted(_BUILTIN_SLUGS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(slug.lower())}\b", haystack):
            return slug
    return ""


def infer_upload_layout_slug(*hints: str, sample_text: str = "") -> str:
    """Choose which Jinja starter to copy into a new upload folder.

    Prefer name match to gallery builtins; otherwise sniff sample text
    (Quang-style \"Professional Summary\" / \"Work Experience\"). Default
    is the generic uploaded (black/white) starter — never green dejan.
    """
    matched = detect_layout_slug(*hints)
    if matched:
        return matched
    lower = (sample_text or "").lower()
    if "professional summary" in lower and "work experience" in lower:
        return "quang"
    return "uploaded"


def resolve_render_layout_slug(template: ResumeTemplate) -> str:
    """Named Jinja slug for PDF render, or '' to use the upload's own Jinja file.

    Private uploads ALWAYS return '' so preview/download use that upload's
    own ``template.html.jinja2`` (a per-upload copy). Built-in gallery rows
    use their coded slug.
    """
    if getattr(template, "source_path", None) and not getattr(template, "is_builtin", False):
        return ""
    stored = (getattr(template, "layout_slug", None) or "").strip()
    if stored and stored != "uploaded" and stored in list_jinja_layout_slugs():
        return stored
    slug = (getattr(template, "slug", None) or "").strip()
    if slug and slug in list_jinja_layout_slugs():
        return slug
    return ""


def _layout_jinja_source(layout_slug: str) -> Path:
    """Source Jinja file for a layout slug (named coded layout or _uploaded)."""
    slug = (layout_slug or "").strip() or "uploaded"
    if slug != "uploaded":
        named = _TEMPLATES_DIR / slug / _UPLOADED_JINJA_NAME
        if named.exists():
            return named
    return _UPLOADED_JINJA_SOURCE


def install_uploaded_jinja_layout(
    dest_dir: Path,
    layout_slug: str = "",
    *,
    force: bool = False,
) -> Path:
    """Install this upload's own ``template.html.jinja2`` into its folder.

    Every private upload gets a distinct file under
    ``user_templates/<user_id>/<slug>/template.html.jinja2``. Starter content
    is copied from the matched layout (quang/mateo/… or ``_uploaded``).
    Pass ``force=True`` on create/repair so Quang and Dejan uploads do not
    keep sharing one identical starter file.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _UPLOADED_JINJA_NAME
    source = _layout_jinja_source(layout_slug or "uploaded")
    if not source.exists():
        raise FileNotFoundError(f"Missing Jinja layout source: {source}")
    if force or not dest.exists():
        shutil.copy2(source, dest)
    return dest


def uploaded_jinja_path(template: ResumeTemplate) -> Path | None:
    """Return the Jinja file for an uploaded template, if present."""
    if not getattr(template, "source_path", None):
        return None
    path = Path(template.source_path).parent / _UPLOADED_JINJA_NAME
    return path if path.exists() else None


def ensure_uploaded_jinja_layout(template: ResumeTemplate) -> Path | None:
    """Ensure this upload has its own Jinja file (create from its layout_slug if missing)."""
    if not getattr(template, "source_path", None):
        return None
    dest_dir = Path(template.source_path).parent
    if not dest_dir.exists():
        return None
    try:
        layout = (getattr(template, "layout_slug", None) or "").strip() or "uploaded"
        if layout not in _BUILTIN_SLUGS and layout != "uploaded":
            layout = (
                infer_upload_layout_slug(
                    getattr(template, "name", ""),
                    getattr(template, "slug", ""),
                    Path(template.source_path).name,
                )
            )
        return install_uploaded_jinja_layout(dest_dir, layout, force=False)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Could not install Jinja layout for upload %s",
            getattr(template, "slug", "?"),
            exc_info=True,
        )
        return None


def _sample_text_hint(source_path: Path) -> str:
    """Best-effort text from an uploaded PDF/DOCX for layout sniffing."""
    try:
        if source_path.suffix.lower() not in {".pdf", ".docx"}:
            return ""
        from app.services.cv_parser import extract_text_from_cv

        return (extract_text_from_cv(source_path) or "")[:4000]
    except Exception:  # noqa: BLE001
        return ""


def repair_uploaded_jinja_layouts() -> int:
    """Give each upload its own Jinja content from name/sample (force refresh).

    \"Quang Dang Resume\" → copy quang Jinja into that folder;
    \"Dejan…\" / unknown → copy uploaded (black/white) Jinja into that folder.
    Always writes the per-upload file so selecting Quang vs Dejan cannot share
    one identical layout.
    """
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
            source = Path(row.source_path)
            dest_dir = source.parent
            if not dest_dir.exists():
                continue
            desired = infer_upload_layout_slug(
                row.name,
                row.slug,
                source.name,
                sample_text=_sample_text_hint(source),
            )
            try:
                install_uploaded_jinja_layout(dest_dir, desired, force=True)
            except Exception:  # noqa: BLE001
                logger.warning("Failed installing Jinja for %s", row.slug, exc_info=True)
                continue
            if (row.layout_slug or "").strip() != desired:
                row.layout_slug = desired
            repaired += 1
    return repaired


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
      template.html.jinja2      — THIS upload's own Jinja (distinct per upload)
      preview.pdf               — thumbnail source

    Starter Jinja is chosen from the sample name/text (Quang → quang copy,
    otherwise uploaded black/white). Selecting this template always renders
    its own ``template.html.jinja2``.
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
    # Sniff after writing source so Quang vs Dejan get different Jinja content
    # in their own folders (still rendered from that folder, never remapped).
    sample_text = _sample_text_hint(source_path)
    layout_slug = infer_upload_layout_slug(original_filename, name, sample_text=sample_text)
    install_uploaded_jinja_layout(dest_dir, layout_slug, force=True)

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

    layout_note = (
        f" Own Jinja layout (starter: {layout_slug})."
        if layout_slug != "uploaded"
        else " Own Jinja layout (uploaded starter)."
    )

    with session_scope() as session:
        has_any = (
            session.query(ResumeTemplate)
            .filter_by(user_id=user_id, is_active=True)
            .count()
        )
        row = ResumeTemplate(
            slug=slug,
            name=name,
            description="Uploaded sample." + layout_note,
            thumbnail_path=thumbnail_path,
            is_active=True,
            user_id=user_id,
            is_builtin=False,
            source_path=str(source_path.resolve()),
            layout_slug=layout_slug,
            is_default=has_any == 0,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        session.expunge(row)
        return row


def repair_uploaded_template_thumbnails(static_dir_path: Path | None = None) -> int:
    """Rebuild missing thumbnails for uploaded templates (wrong path / failed convert).

    Also syncs layout_slug to the inferred starter (quang/mateo/… or uploaded)
    without changing how render resolves (uploads still use their own file).
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
            source = Path(row.source_path) if row.source_path else None
            desired = (
                infer_upload_layout_slug(
                    row.name,
                    row.slug,
                    source.name if source else "",
                    sample_text=_sample_text_hint(source) if source and source.exists() else "",
                )
                if row.source_path
                else stored
            )
            if row.source_path and stored != desired:
                row.layout_slug = desired
                repaired += 1
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
    """Permanently remove an uploaded template and all related files.

    Deletes:
      - DB row
      - upload folder (source.pdf|docx, preview.pdf, template.html.jinja2, working.docx)
      - gallery thumbnail under static/template_previews/<slug>.png
    Built-ins cannot be deleted.
    """
    static_dir_path = static_dir()
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
        thumb_rel = (row.thumbnail_path or "").strip()
        session.delete(row)
        session.flush()
        if was_default:
            replacement = (
                session.query(ResumeTemplate)
                .filter_by(user_id=user_id, is_active=True)
                .order_by(ResumeTemplate.slug)
                .first()
            )
            if replacement is not None:
                replacement.is_default = True

    if source is not None:
        folder = source.parent
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
    if thumb_rel:
        thumb = static_dir_path / thumb_rel
        try:
            thumb.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.warning("Could not delete thumbnail %s", thumb, exc_info=True)
    # Also remove by slug convention in case thumbnail_path was empty/stale.
    try:
        (static_dir_path / _THUMBNAIL_DIRNAME / f"{slug}.png").unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def delete_templates_for_user(user_id: int) -> None:
    """Hard-delete every template owned by this user (files + DB rows)."""
    static_dir_path = static_dir()
    with session_scope() as session:
        rows = session.query(ResumeTemplate).filter_by(user_id=user_id).all()
        for row in rows:
            if row.source_path:
                path = Path(row.source_path)
                folder = path.parent
                if folder.exists():
                    shutil.rmtree(folder, ignore_errors=True)
            thumb_rel = (row.thumbnail_path or "").strip()
            if thumb_rel:
                try:
                    (static_dir_path / thumb_rel).unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
            if row.slug:
                try:
                    (static_dir_path / _THUMBNAIL_DIRNAME / f"{row.slug}.png").unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
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
