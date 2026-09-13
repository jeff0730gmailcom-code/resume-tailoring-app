"""Render a filled DOCX (uploaded template) to PDF without requiring Word.

Primary path still prefers Word COM when available. When Word is missing
or fails (common on Railway/Linux and some local setups), convert the
filled DOCX to HTML and print it with Playwright — the same engine used
for built-in Jinja templates.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.models.schemas import TailoredResumeContent
from app.services.docx_template_fill import fill_docx_template
from app.services.docx_to_pdf import convert_docx_to_pdf, convert_to_docx
from app.services.template_registry import resolve_working_docx
from app.services.template_renderer import render_html_to_pdf, render_pdf

logger = logging.getLogger(__name__)

_FALLBACK_BUILTIN_SLUG = "mateo"


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
    @page {{ size: A4; margin: 14mm 16mm; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{
      font-family: Calibri, "Segoe UI", Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.35;
      color: #222;
    }}
    p {{ margin: 0 0 0.35em; }}
    ul {{ margin: 0.2em 0 0.6em 1.2em; padding: 0; }}
    li {{ margin: 0 0 0.2em; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ vertical-align: top; padding: 0; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


async def render_uploaded_template_pdf(
    *,
    file_id: str,
    template,
    tailored: TailoredResumeContent,
    work_dir: Path,
) -> bytes | None:
    """Fill the uploaded sample CV and produce PDF bytes.

    Order:
    1. Ensure a working DOCX exists (convert PDF→DOCX via Word when needed)
    2. Fill tailored content into that DOCX
    3. Word DOCX→PDF when available
    4. mammoth HTML → Playwright PDF (no Word)
    5. Built-in Mateo Jinja → Playwright PDF (last resort so preview never dies)
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    filled_docx = work_dir / "filled_template.docx"
    filled_pdf = work_dir / "filled_template.pdf"

    working = resolve_working_docx(template)
    if working is None or not working.exists():
        source = Path(template.source_path) if getattr(template, "source_path", None) else None
        if source is not None and source.exists():
            working = source.parent / "working.docx"
            if source.suffix.lower() == ".docx":
                shutil.copy2(source, working)
            else:
                ok = await convert_to_docx(source, working)
                if not ok or not working.exists():
                    working = None
        else:
            working = None

    if working is not None and working.exists():
        try:
            fill_docx_template(working, filled_docx, tailored)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fill uploaded template %s", getattr(template, "slug", "?"))
            filled_docx = None  # type: ignore[assignment]
    else:
        filled_docx = None  # type: ignore[assignment]
        logger.warning(
            "No working DOCX for uploaded template %s — falling back to built-in layout",
            getattr(template, "slug", "?"),
        )

    if filled_docx is not None and filled_docx.exists():
        # 1) Word COM when present
        ok = await convert_docx_to_pdf(filled_docx, filled_pdf)
        if ok and filled_pdf.exists() and filled_pdf.stat().st_size > 0:
            return filled_pdf.read_bytes()

        # 2) mammoth + Playwright (no Word)
        try:
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

    # 3) Reliable built-in layout so preview/download still work
    logger.warning(
        "Using built-in '%s' layout for uploaded template %s",
        _FALLBACK_BUILTIN_SLUG,
        getattr(template, "slug", "?"),
    )
    return await render_pdf(_FALLBACK_BUILTIN_SLUG, tailored)
