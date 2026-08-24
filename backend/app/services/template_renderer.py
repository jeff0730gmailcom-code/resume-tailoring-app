"""Render tailored resume content into a selected template.

Two steps:
1. Jinja2 fills app/templates/resumes/<slug>/template.html.jinja2 with the
   TailoredResumeContent fields (same schema used everywhere else in the
   app - see app/models/schemas.py, no changes needed there).
2. A warm, shared Playwright Chromium instance (started/stopped in
   app/main.py's lifespan - the same "keep one warm instance across
   requests" pattern this project already uses for Word COM, see
   app/services/docx_to_pdf.py) renders that HTML to PDF bytes.

DOCX output is deliberately NOT a second hand-built renderer: callers
convert the already-rendered PDF to .docx via
app/services/docx_to_pdf.convert_to_docx (Word COM), reusing that existing,
working conversion path instead of maintaining a parallel python-docx
template per design.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import Browser, async_playwright

# Linux containers (Render, Hugging Face, Docker) cannot run Chromium in
# a sandbox, and /dev/shm is often too small. Harmless on Windows.
_CHROMIUM_ARGS = ["--disable-dev-shm-usage"]
if sys.platform != "win32":
    _CHROMIUM_ARGS.append("--no-sandbox")

from app.models.schemas import TailoredResumeContent
from app.services.cv_structurer import clip_job_company, clip_job_title
from app.services.text_sanitize import strip_broken_characters, strip_broken_from_tree

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "resumes"

# Page margins are declared entirely in each template's own CSS via
# "@page { margin: ... } @page :first { margin-top: ... }" - deliberately
# NOT passed here via Playwright's page.pdf() margin option. Two reasons:
# 1. This Chromium build lets a CSS "@page" margin rule silently override
#    the JS margin option (observed even when the CSS rule sets margin to
#    0) - so mixing both is unreliable; one mechanism must own it fully.
# 2. Only CSS's "@page :first" pseudo-class can give page 1 a different
#    (smaller) top margin than every later page (bigger, so a section/job
#    that spills onto a new page never starts flush against the edge) -
#    the JS margin option is a single value applied uniformly to every
#    page, with no way to special-case page 1 vs. the rest.
# See each template's <style> block for the actual values.

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "jinja2"]),
)

_playwright = None
_browser: Browser | None = None


async def start_browser() -> None:
    """Launch the shared warm Chromium instance. Call once, on app
    startup.

    Tries Playwright's bundled Chromium first (`playwright install chromium`).
    If that binary is missing or the download failed (common on flaky
    networks - ECONNRESET against cdn.playwright.dev), falls back to a
    Chrome/Edge already installed on this machine via Playwright's
    `channel=` option. PDF rendering is the same Chromium print engine
    either way."""
    global _playwright, _browser
    if _browser is not None:
        return
    try:
        _playwright = await async_playwright().start()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start Playwright - PDF rendering will be unavailable")
        _playwright, _browser = None, None
        return

    last_error: Exception | None = None
    for label, kwargs in (
        ("bundled Chromium", {}),
        ("system Chrome", {"channel": "chrome"}),
        ("system Edge", {"channel": "msedge"}),
    ):
        try:
            _browser = await _playwright.chromium.launch(**kwargs, args=_CHROMIUM_ARGS)
            logger.info("Playwright launched %s for resume template rendering", label)
            return
        except Exception as exc:  # noqa: BLE001 - try the next browser
            last_error = exc
            logger.warning("Could not launch Playwright via %s: %s", label, exc)

    logger.exception(
        "Failed to launch Playwright Chromium/Chrome/Edge - PDF rendering will be unavailable",
        exc_info=last_error,
    )
    try:
        await _playwright.stop()
    except Exception:  # noqa: BLE001
        pass
    _playwright, _browser = None, None


async def stop_browser() -> None:
    """Cleanly close the shared Chromium instance on app shutdown."""
    global _playwright, _browser
    try:
        if _browser is not None:
            await _browser.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        if _playwright is not None:
            await _playwright.stop()
    except Exception:  # noqa: BLE001
        pass
    _browser, _playwright = None, None


_JUNK_PREFIX_RE = re.compile(
    r"^[\s\ufeff\ufffd\u25a0\u25a1\u25aa\u25ab\u25cf\u25e6\u2022•●◦○□■▪▫?\-]+\s*"
)
_MAJOR_PREFIX_RE = re.compile(r"^(major|degree|field of study)\s*:\s*", re.IGNORECASE)


def render_html(slug: str, resume: TailoredResumeContent) -> str:
    template = _env.get_template(f"{slug}/template.html.jinja2")
    return template.render(resume=_sanitize_resume_text(resume))


def _sanitize_resume_text(resume: TailoredResumeContent) -> TailoredResumeContent:
    """Drop PDF-extraction junk so templates never render a broken square
    or a packed 'Major: … | DEGREE | SCHOOL' education line."""
    data = strip_broken_from_tree(resume.model_dump())
    for edu in data.get("education") or []:
        for key in ("degree", "institution", "dates"):
            if edu.get(key):
                edu[key] = _clean_field(edu[key])
    for job in data.get("experience") or []:
        title = clip_job_title(job.get("title") or "")
        job["title"] = title
        job["company"] = clip_job_company(job.get("company") or "", title)
        job["dates"] = strip_broken_characters(job.get("dates") or "")
        cleaned_bullets = []
        for bullet in job.get("bullets") or []:
            text = strip_broken_characters(_JUNK_PREFIX_RE.sub("", str(bullet)).strip())
            if text:
                cleaned_bullets.append(text)
        job["bullets"] = cleaned_bullets
    return TailoredResumeContent.model_validate(data)


def _clean_field(text: str) -> str:
    cleaned = strip_broken_characters(text)
    cleaned = _JUNK_PREFIX_RE.sub("", cleaned)
    cleaned = _MAJOR_PREFIX_RE.sub("", cleaned)
    return strip_broken_characters(cleaned.strip(" |,-–—"))


async def render_pdf(slug: str, resume: TailoredResumeContent) -> bytes | None:
    """Render the selected template with this resume's content to PDF
    bytes. Returns None if the shared browser isn't available (Chromium
    not installed / failed to launch) - callers should treat that as a
    soft failure, same spirit as docx_to_pdf's boolean-returning
    conversions."""
    if _browser is None:
        logger.error("render_pdf called but Playwright browser is not running")
        return None

    html = render_html(slug, resume)
    page = await _browser.new_page()
    try:
        await page.set_content(html, wait_until="load")
        # No margin= here on purpose - the template's own CSS "@page" rule
        # is the sole source of page margins (see the module docstring
        # above the removed _PAGE_MARGINS constant for why).
        return await page.pdf(format="A4", print_background=True)
    finally:
        await page.close()
