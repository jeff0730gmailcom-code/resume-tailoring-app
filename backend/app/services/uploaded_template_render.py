"""Render a filled DOCX (uploaded template) to PDF.

Order:
1. Ensure working.docx (copy DOCX, or Word PDF→DOCX with retry)
2. Fill the sample with tailored content (preserves layout)
3. Export PDF via mammoth HTML → Playwright (same engine as Mateo/Marek)
4. If Playwright fails, try Word DOCX→PDF

Uploads are never remapped to a different coded Jinja layout.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.models.schemas import TailoredResumeContent
from app.services.docx_template_fill import fill_docx_template
from app.services.docx_to_pdf import convert_docx_to_pdf, convert_to_docx
from app.services.template_registry import resolve_working_docx
from app.services.template_renderer import render_html_to_pdf

logger = logging.getLogger(__name__)


def _docx_to_print_html(docx_path: Path) -> str:
    """Best-effort DOCX → HTML for Playwright printing."""
    try:
        import mammoth
    except ImportError:
        raise RuntimeError("mammoth is not installed") from None

    with docx_path.open("rb") as handle:
        result = mammoth.convert_to_html(handle)
    body = result.value or ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    @page {{ size: A4; margin: 16mm 14mm; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", Calibri, Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.45;
      color: #1a1a1a;
    }}
    p {{ margin: 0 0 0.35em; }}
    strong {{ font-weight: 700; }}
    ul {{ margin: 0.25em 0 0.7em 1.15em; padding: 0; }}
    li {{ margin: 0 0 0.25em; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ vertical-align: top; padding: 0; }}
    hr {{ border: none; border-top: 1px solid #999; margin: 10px 0 6px; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


async def _ensure_working_docx(template) -> Path | None:
    working = resolve_working_docx(template)
    if working is not None and working.exists() and working.stat().st_size > 0:
        return working

    source = Path(template.source_path) if getattr(template, "source_path", None) else None
    if source is None or not source.exists():
        return None

    working = source.parent / "working.docx"
    if source.suffix.lower() == ".docx":
        shutil.copy2(source, working)
        return working if working.exists() and working.stat().st_size > 0 else None

    from app.services.docx_to_pdf import _recover_from_hang

    ok = await convert_to_docx(source, working)
    if (not ok or not working.exists()) and source.suffix.lower() == ".pdf":
        logger.warning(
            "Retrying PDF→DOCX for uploaded template %s after Word recover",
            getattr(template, "slug", "?"),
        )
        _recover_from_hang()
        working.unlink(missing_ok=True)
        ok = await convert_to_docx(source, working)

    if ok and working.exists() and working.stat().st_size > 0:
        return working
    return None


async def _filled_docx_to_pdf(filled_docx: Path, filled_pdf: Path) -> bytes | None:
    """Export filled DOCX to PDF. Prefer Playwright (Mateo-style); Word is backup."""
    try:
        html = _docx_to_print_html(filled_docx)
        pdf_bytes = await render_html_to_pdf(html)
        if pdf_bytes:
            filled_pdf.write_bytes(pdf_bytes)
            return pdf_bytes
    except Exception:  # noqa: BLE001
        logger.warning(
            "mammoth/Playwright export failed for %s",
            filled_docx,
            exc_info=True,
        )

    ok = await convert_docx_to_pdf(filled_docx, filled_pdf)
    if ok and filled_pdf.exists() and filled_pdf.stat().st_size > 0:
        return filled_pdf.read_bytes()

    return None


async def render_uploaded_template_pdf(
    *,
    file_id: str,
    template,
    tailored: TailoredResumeContent,
    work_dir: Path,
) -> bytes | None:
    """Fill the uploaded sample CV and produce PDF bytes."""
    work_dir.mkdir(parents=True, exist_ok=True)
    filled_docx = work_dir / "filled_template.docx"
    filled_pdf = work_dir / "filled_template.pdf"
    slug = getattr(template, "slug", "?")
    name = getattr(template, "name", "")

    working = await _ensure_working_docx(template)
    if working is None:
        logger.warning(
            "Uploaded template %s (%s) has no working DOCX — cannot fill the sample layout",
            slug,
            name,
        )
        return None

    try:
        fill_docx_template(working, filled_docx, tailored)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fill uploaded template %s", slug)
        return None

    if not filled_docx.exists() or filled_docx.stat().st_size <= 0:
        logger.warning("Fill produced no DOCX for uploaded template %s", slug)
        return None

    pdf_bytes = await _filled_docx_to_pdf(filled_docx, filled_pdf)
    if pdf_bytes:
        return pdf_bytes

    logger.error(
        "Uploaded template %s was filled but PDF export failed (Playwright and Word)",
        slug,
    )
    return None
