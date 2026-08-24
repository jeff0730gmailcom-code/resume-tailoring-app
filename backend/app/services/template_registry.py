"""Resume template registry: seeds app/db/models.py's ResumeTemplate rows
from the on-disk template folders, and lists/looks them up for the API.

Each template lives at app/templates/resumes/<slug>/, containing:
- template.html.jinja2 - the Jinja2 layout used to render tailored content
  (see app/services/template_renderer.py).
- reference.pdf - the original sample CV this design was modeled on. Its
  first page is rasterized (via PyMuPDF) into the gallery thumbnail, so
  the picker shows the real sample resume, not a synthetic re-render.

Human-readable name/description per slug lives in _TEMPLATE_META below -
kept here (not inferred from the folder) since it's the only piece that
isn't mechanically derivable from the template files themselves.
"""
from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

from app.db.models import ResumeTemplate
from app.db.session import session_scope

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "resumes"
_THUMBNAIL_DIRNAME = "template_previews"

# slug -> (display name, short description shown under the thumbnail).
_TEMPLATE_META: dict[str, tuple[str, str]] = {
    "aleksandra": ("PHP Lead", "Single-column layout with a green name, all-caps section headings, and grouped skills."),
    "dejan": ("Modern Green", "Clean single-column layout with a green accent bar and bold section headings."),
    "goran": ("Frontend Serif", "Teal serif name and headings, pipe-separated job lines, and categorized skills."),
    "luka": ("Two-Column Lead", "Name header with a two-column layout: orange section labels and a light sidebar."),
    "marek": ("Classic Serif", "Traditional black & white layout with a serif font and bold inline keyword emphasis."),
    "mateo": ("Bold Header", "Large two-line name with top-right contact icons and a colored job-title line."),
    "nemanja": ("Centered Rule", "Fully centered header and contact row, with underlined all-caps section headings."),
    "quang": ("Teal Centered", "Centered teal header and contact row, with underlined teal section headings."),
}


def _thumbnail_dir(static_dir: Path) -> Path:
    path = static_dir / _THUMBNAIL_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_thumbnail(slug: str, reference_pdf: Path, static_dir: Path) -> str:
    """Rasterize reference_pdf's first page to a PNG thumbnail if one
    doesn't already exist. Returns the path relative to static_dir (the
    value stored in ResumeTemplate.thumbnail_path)."""
    relative_path = f"{_THUMBNAIL_DIRNAME}/{slug}.png"
    thumbnail_path = static_dir / relative_path
    if thumbnail_path.exists():
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


def seed_templates_from_disk(static_dir: Path) -> None:
    """Scan app/templates/resumes/*/ and upsert a ResumeTemplate row (plus
    its thumbnail) for each folder found. Idempotent - safe to call on
    every startup."""
    if not _TEMPLATES_DIR.exists():
        logger.warning("Template directory %s does not exist - no templates seeded", _TEMPLATES_DIR)
        return

    with session_scope() as session:
        for template_dir in sorted(_TEMPLATES_DIR.iterdir()):
            if not template_dir.is_dir():
                continue
            slug = template_dir.name
            html_path = template_dir / "template.html.jinja2"
            reference_pdf = template_dir / "reference.pdf"
            if not html_path.exists() or not reference_pdf.exists():
                logger.warning("Skipping template %r - missing template.html.jinja2 or reference.pdf", slug)
                continue

            name, description = _TEMPLATE_META.get(slug, (slug.title(), ""))
            thumbnail_path = _ensure_thumbnail(slug, reference_pdf, static_dir)

            existing = session.query(ResumeTemplate).filter_by(slug=slug).one_or_none()
            if existing is None:
                session.add(
                    ResumeTemplate(
                        slug=slug,
                        name=name,
                        description=description,
                        thumbnail_path=thumbnail_path,
                    )
                )
            else:
                existing.name = name
                existing.description = description
                existing.thumbnail_path = thumbnail_path
                existing.is_active = True


def list_templates() -> list[ResumeTemplate]:
    """All active templates, most recently added last (stable slug order)."""
    with session_scope() as session:
        rows = (
            session.query(ResumeTemplate)
            .filter_by(is_active=True)
            .order_by(ResumeTemplate.slug)
            .all()
        )
        session.expunge_all()
        return rows


def get_template(slug: str) -> ResumeTemplate | None:
    with session_scope() as session:
        row = session.query(ResumeTemplate).filter_by(slug=slug, is_active=True).one_or_none()
        if row is not None:
            session.expunge(row)
        return row


def get_template_by_id(template_id: int) -> ResumeTemplate | None:
    with session_scope() as session:
        row = session.query(ResumeTemplate).filter_by(id=template_id).one_or_none()
        if row is not None:
            session.expunge(row)
        return row
