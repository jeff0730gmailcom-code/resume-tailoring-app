"""Render a filled DOCX (uploaded template) to PDF.

Order:
1. Fill the uploaded sample DOCX with tailored content (preserves their layout)
2. Word DOCX→PDF when available
3. mammoth HTML → Playwright PDF (no Word)

Uploads are never remapped to a different coded Jinja layout (e.g. a file
named Dejan Pavlovic.pdf must not silently render templates/resumes/dejan/).
If the sample cannot be filled, return None so the API can ask for a DOCX.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.models.schemas import TailoredResumeContent
from app.services.docx_template_fill import fill_docx_template
from app.services.docx_to_pdf import convert_docx_to_pdf, convert_to_docx
from app.services.template_registry import resolve_working_docx
from app.services.template_renderer import ensure_browser, render_html_to_pdf

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

    # PDF/DOC samples need Word. Retry once after a COM hang recovery — upload-time
    # conversion often fails when Word is busy, then succeeds on generate.
    from app.services.docx_to_pdf import _recover_from_hang

    ok = await convert_to_docx(source, working)
    if (not ok or not working.exists()) and source.suffix.lower() == ".pdf":
        logger.warning("Retrying PDF→DOCX for uploaded template %s after Word recover", getattr(template, "slug", "?"))
        _recover_from_hang()
        working.unlink(missing_ok=True)
        ok = await convert_to_docx(source, working)

    if ok and working.exists() and working.stat().st_size > 0:
        return working
    return None


async def render_uploaded_template_pdf(
    *,
    file_id: str,
    template,
    tailored: TailoredResumeContent,
    work_dir: Path,
) -> bytes | None:
    """Fill the uploaded sample CV and produce PDF bytes.

    Returns None when the upload cannot be filled (no working DOCX). Callers
    must not substitute a different person's Jinja template.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    filled_docx = work_dir / "filled_template.docx"
    filled_pdf = work_dir / "filled_template.pdf"

    working = await _ensure_working_docx(template)
    if working is None:
        logger.warning(
            "Uploaded template %s (%s) has no working DOCX — cannot fill the sample layout",
            getattr(template, "slug", "?"),
            getattr(template, "name", ""),
        )
        return None

    try:
        fill_docx_template(working, filled_docx, tailored)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fill uploaded template %s", getattr(template, "slug", "?"))
        return None

    if not filled_docx.exists():
        return None

    ok = await convert_docx_to_pdf(filled_docx, filled_pdf)
    if ok and filled_pdf.exists() and filled_pdf.stat().st_size > 0:
        return filled_pdf.read_bytes()

    try:
        await ensure_browser()
        html = _docx_to_print_html(filled_docx)
        pdf_bytes = await render_html_to_pdf(html)
        if pdf_bytes:
            filled_pdf.write_bytes(pdf_bytes)
            return pdf_bytes
    except Exception:  # noqa: BLE001
        logger.warning(
            "mammoth/Playwright PDF path failed for uploaded template %s",
            getattr(template, "slug", "?"),
            exc_info=True,
        )

    return None
