"""Resume tailoring endpoints: upload CV -> pick a template -> tailor with
AI -> download resume (PDF or DOCX).

Maps onto this pipeline (see app/utils/timing.py for the exact report
format each step is timed against):

  1. CV Parsing        - /upload  (one-time per CV: parse, structure, cache)
  2. JD Analysis        - /tailor (no AI)
  3. Resume Matching     - /tailor (no AI)
  4. Prompt Build        - /tailor (inside ai_tailor.tailor_resume)
  5. OpenAI              - /tailor (inside ai_tailor.tailor_resume - ONE call)
  6. Validation          - /tailor (ATS re-scoring + resume_validator checks)
  7. PDF Generation      - /download (Jinja2 template + Playwright render)
  8. DOCX Generation     - /download (only when format=docx: Word COM
                            converts the just-rendered PDF, see
                            app/services/docx_to_pdf.convert_to_docx)
  9. Response            - /download (return the file to the browser)

Since steps 2-9 span three separate HTTP requests (upload/tailor/download),
each step's duration is persisted per file_id (see file_utils.save_perf_stages)
and carried forward, so /tailor's and /download's printed reports are
cumulative - /download's report covers the whole pipeline end to end.

The master CV is a content source only (see app/services/cv_structurer.py) -
its own visual layout is never preserved. Instead, the tailored content is
rendered into a separately-selected HTML/CSS template (see
app/services/template_renderer.py and app/services/template_registry.py).
"""
import asyncio
import logging
from pathlib import Path
from urllib.parse import quote

from docx import Document as DocxDocument
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.models.schemas import ResumeMetadata, ResumeTemplateInfo, TailorRequest, TailorResponse, UploadResponse
from app.services.ai_application_answers import generate_application_answers, normalize_application_questions
from app.services.ai_cover_letter import generate_cover_letter
from app.services.ai_tailor import AiTailoringError, tailor_resume
from app.services.ats_scorer import compute_ats_match
from app.services.cv_parser import CvParsingError, extract_text_from_cv
from app.services.cv_structurer import structure_cv
from app.services.docx_to_pdf import convert_to_docx
from app.services.filename_generator import generate_resume_cv_stem, generate_resume_filename, generate_resume_folder_name
from app.services.jd_analyzer import analyze_job_description
from app.services.resume_matcher import match_resume_to_jd
from app.services.resume_records import get_latest_resume_record, list_resume_records, save_resume_record
from app.services.resume_validator import close_ats_gaps, validate_and_fix_resume
from app.services.template_registry import get_template, get_template_by_id, list_templates
from app.services.template_renderer import render_pdf
from app.utils import file_utils
from app.utils.timing import PerfReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resume", tags=["resume"])


@router.get("/templates", response_model=list[ResumeTemplateInfo])
async def resume_templates() -> list[ResumeTemplateInfo]:
    """List every selectable resume template for the frontend gallery (see
    app/services/template_registry.seed_templates_from_disk, run at
    startup). thumbnail_url is a path under the /static mount (see
    app/main.py) - the frontend prefixes it with its API base URL."""
    return [
        ResumeTemplateInfo(
            slug=t.slug,
            name=t.name,
            description=t.description,
            thumbnail_url=f"/static/{t.thumbnail_path}",
        )
        for t in list_templates()
    ]


@router.post("/upload", response_model=UploadResponse)
async def upload_cv(file: UploadFile = File(...)) -> UploadResponse:
    """Step 1 (one-time per CV): parse the document, extract text, convert
    to structured JSON (no AI - see cv_structurer.py), and cache everything
    under a generated file id so /tailor never has to re-parse or re-send
    the raw CV.

    The master CV is a content source only - its layout is never preserved
    or edited; see the module docstring."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in file_utils.ALLOWED_CV_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Please upload a PDF, DOC, or DOCX master CV.",
        )

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File is too large. Max size is {settings.max_upload_size_mb}MB.",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    perf = PerfReport(label=f"upload:{file.filename}")

    file_id = file_utils.generate_temp_file_id()
    original_path = file_utils.save_upload(file_id, file.filename or f"cv{suffix}", content)

    shared_document = None
    if suffix == ".docx":
        try:
            shared_document = await asyncio.to_thread(DocxDocument, str(original_path))
        except Exception:  # noqa: BLE001 - structuring falls back to raw text below
            shared_document = None

    with perf.stage("CV Parsing"):
        try:
            cv_text = await asyncio.to_thread(extract_text_from_cv, original_path, shared_document)
        except CvParsingError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        master_cv = await asyncio.to_thread(structure_cv, original_path, cv_text, shared_document)

    file_utils.save_cv_text(file_id, cv_text)
    file_utils.save_master_cv(file_id, master_cv)
    file_utils.save_perf_stages(file_id, perf.snapshot())

    perf.log()

    return UploadResponse(
        file_id=file_id,
        file_name=file.filename or original_path.name,
        cv_text_preview=cv_text[:400],
    )


@router.post("/tailor", response_model=TailorResponse)
async def tailor(payload: TailorRequest) -> TailorResponse:
    """Steps 2-6: analyze the JD (no AI), match it against the cached
    structured CV (no AI), build the prompt, make the single OpenAI
    request, then validate/auto-fix the result (no AI)."""
    if not payload.job_description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job description cannot be empty.")
    if not payload.main_stack.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Main technology stack cannot be empty.")
    if not payload.company_name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target company name cannot be empty.")
    if not payload.template_slug.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please select a resume template.")

    template = get_template(payload.template_slug)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown resume template '{payload.template_slug}'.",
        )

    master_cv = file_utils.load_master_cv(payload.file_id)
    if master_cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV not found for this file_id. Please upload your CV again.",
        )

    perf = PerfReport(label=f"tailor:{payload.file_id} mode={settings.tailoring_mode}")
    perf.seed(file_utils.load_perf_stages(payload.file_id))

    mode = settings.tailoring_mode

    with perf.stage("JD Analysis"):
        jd_analysis = analyze_job_description(payload.job_description)

    with perf.stage("Resume Matching"):
        resume_match = match_resume_to_jd(master_cv, jd_analysis, mode=mode)

    try:
        tailored, ats_match = await tailor_resume(
            master_cv, jd_analysis, resume_match, payload.job_description, None, perf=perf, mode=mode
        )
    except AiTailoringError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    with perf.stage("Validation"):
        validation = validate_and_fix_resume(tailored, master_cv, None)

        # Deterministic ATS / preferred-skill coverage (no second OpenAI call):
        # Skills + Summary pick up every CV-supported matched/transferable
        # term, with preferred/nice-to-haves prioritized, then re-score.
        gap_fixes = close_ats_gaps(tailored, resume_match, master_cv)
        if gap_fixes:
            validation.issues.extend(gap_fixes)
        ats_match = compute_ats_match(tailored, payload.job_description, jd_analysis)

    if not validation.is_clean:
        logger.warning("Resume validation auto-corrected issues for %s: %s", payload.file_id, validation.issues)

    file_utils.save_tailored_resume(payload.file_id, tailored)

    cover_letter = None
    if payload.include_cover_letter:
        try:
            cover_letter = await generate_cover_letter(
                tailored,
                jd_analysis,
                payload.job_description,
                payload.company_name,
                perf=perf,
            )
            file_utils.save_cover_letter(payload.file_id, cover_letter)
        except Exception as exc:  # noqa: BLE001 - letter is optional; never drop the resume
            logger.warning("Cover letter generation failed for %s: %s", payload.file_id, exc)

    application_answers = []
    questions = normalize_application_questions(payload.application_questions)
    if questions:
        try:
            application_answers = await generate_application_answers(
                tailored,
                jd_analysis,
                payload.job_description,
                payload.company_name,
                questions,
                perf=perf,
            )
            file_utils.save_application_answers(payload.file_id, application_answers)
        except Exception as exc:  # noqa: BLE001 - answers are optional; never drop the resume
            logger.warning("Application answers generation failed for %s: %s", payload.file_id, exc)

    file_utils.save_perf_stages(payload.file_id, perf.snapshot())

    # Deterministic (no AI) filename generation - see
    # app/services/filename_generator.py. The stored base name (no
    # extension) is reused by /download for both the PDF and DOCX export,
    # and also recorded as this file_id's latest ResumeRecord.
    generated_filename = generate_resume_filename(tailored.contact.name, payload.main_stack, payload.company_name)
    save_resume_record(
        file_id=payload.file_id,
        template_id=template.id,
        candidate_name=tailored.contact.name,
        main_stack=payload.main_stack.strip(),
        company_name=payload.company_name.strip(),
        generated_filename=generated_filename,
    )

    perf.log()

    return TailorResponse(
        file_id=payload.file_id,
        resume=tailored,
        ats_match=ats_match,
        generated_filename=generated_filename,
        template_slug=template.slug,
        cover_letter=cover_letter,
        application_answers=application_answers,
    )


@router.get("/history", response_model=list[ResumeMetadata])
async def resume_history() -> list[ResumeMetadata]:
    """Resume-generation history (see app/db/models.py's ResumeRecord),
    most recent first."""
    records = list_resume_records()
    slug_by_template_id = {t.id: t.slug for t in list_templates()}
    return [
        ResumeMetadata(
            candidate_name=record.candidate_name,
            main_stack=record.main_stack,
            company_name=record.company_name,
            generated_filename=record.generated_filename,
            template_slug=slug_by_template_id.get(record.template_id, "unknown"),
            created_at=record.created_at.isoformat(),
        )
        for record in records
    ]


async def _render_and_cache_pdf(file_id: str, perf: PerfReport):
    """Shared by /download and /preview: load the tailored content + its
    selected template, render it through the exact same Jinja2 + Playwright
    pipeline, cache the bytes to disk, and return (pdf_path, resume_record).
    """
    tailored = file_utils.load_tailored_resume(file_id)
    if tailored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tailored resume found for this file_id. Please generate one first.",
        )

    record = get_latest_resume_record(file_id)
    if record is None or record.template_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No resume template was selected for this file. Please tailor again after picking a template.",
        )
    template = get_template_by_id(record.template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The selected resume template no longer exists.")

    pdf_path = file_utils.get_tailored_pdf_path(file_id)
    with perf.stage("PDF Generation"):
        pdf_bytes = await render_pdf(template.slug, tailored)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not render the resume PDF. Install Google Chrome or Microsoft Edge, or run `playwright install chromium`.",
        )
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path, record


@router.get("/preview/{file_id}")
async def preview_resume_pdf(file_id: str) -> FileResponse:
    """Live in-app preview: renders the tailored resume with the exact same
    Jinja2 + Playwright pipeline used by /download, and serves it inline
    (Content-Disposition: inline) so the frontend can embed it directly in
    an <iframe>. This guarantees the preview is pixel-identical to the
    downloaded PDF - unlike a hand-rolled HTML preview, it also correctly
    reflects the templates' print-only @page rules (margins, pagination,
    repeating headers) which only apply during PDF rendering."""
    perf = PerfReport(label=f"preview:{file_id}")
    perf.seed(file_utils.load_perf_stages(file_id))
    pdf_path, record = await _render_and_cache_pdf(file_id, perf)
    cv_stem = generate_resume_cv_stem(record.candidate_name)
    perf.log()
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{cv_stem}.pdf",
        content_disposition_type="inline",
    )


@router.post("/download/{file_id}")
async def download_resume(
    file_id: str,
    format: str = Query("pdf", pattern="^(pdf|docx)$", description="'pdf' (default) or 'docx'"),
) -> FileResponse:
    """Steps 7-9: render the tailored content into the template selected at
    /tailor time (Jinja2 + Playwright -> PDF), and - only when
    format=docx - additionally convert that rendered PDF to an editable
    .docx via Word COM (app/services/docx_to_pdf.convert_to_docx). The
    file is returned to the browser so it can be saved on the user's
    computer — never written to the server's (Railway container) disk.
    """
    perf = PerfReport(label=f"download:{file_id}:{format}")
    perf.seed(file_utils.load_perf_stages(file_id))

    pdf_path, record = await _render_and_cache_pdf(file_id, perf)
    folder_name = generate_resume_folder_name(record.candidate_name, record.main_stack, record.company_name)
    cv_stem = generate_resume_cv_stem(record.candidate_name)

    if format == "docx":
        source_path = file_utils.get_tailored_docx_path(file_id)
        with perf.stage("DOCX Generation"):
            docx_ok = await convert_to_docx(pdf_path, source_path)
        if not docx_ok:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not convert the rendered PDF to DOCX. Make sure Microsoft Word is installed.",
            )
        inner_name = f"{cv_stem}.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        source_path = pdf_path
        inner_name = f"{cv_stem}.pdf"
        media_type = "application/pdf"

    response = FileResponse(
        path=source_path,
        media_type=media_type,
        filename=inner_name,
        content_disposition_type="attachment",
    )
    response.headers["X-Resume-Folder-Name"] = quote(folder_name, safe="")
    response.headers["X-Resume-File-Name"] = quote(inner_name, safe="")

    with perf.stage("Response"):
        file_utils.save_perf_stages(file_id, perf.snapshot())

    perf.log()
    return response
