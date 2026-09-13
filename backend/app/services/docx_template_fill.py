"""Fill an uploaded DOCX sample CV with tailored resume content.

Used when the selected template is a user-uploaded PDF/DOCX (not a built-in
Jinja layout). Preserves the sample's formatting by rewriting paragraph
runs in place after structural segmentation.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph

from app.models.schemas import SkillCategories, TailoredResumeContent
from app.services.docx_segmenter import DocxSegments, segment_document

logger = logging.getLogger(__name__)


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    text = (text or "").strip()
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _skills_lines(skills: SkillCategories) -> list[str]:
    labels = (
        ("Languages", skills.languages),
        ("Backend", skills.backend),
        ("Frontend", skills.frontend),
        ("Cloud", skills.cloud),
        ("DevOps", skills.devops),
        ("Databases", skills.databases),
        ("AI", skills.ai),
        ("Tools", skills.tools),
    )
    lines: list[str] = []
    for label, values in labels:
        cleaned = [v.strip() for v in values if v and v.strip()]
        if cleaned:
            lines.append(f"{label}: {', '.join(cleaned)}")
    if not lines:
        flat = []
        for values in (
            skills.languages,
            skills.backend,
            skills.frontend,
            skills.cloud,
            skills.devops,
            skills.databases,
            skills.ai,
            skills.tools,
        ):
            flat.extend(v.strip() for v in values if v and v.strip())
        if flat:
            lines.append(", ".join(flat))
    return lines


def _apply_summary(segments: DocxSegments, summary: str) -> None:
    if not segments.summary_paragraphs:
        return
    summary = (summary or "").strip()
    if not summary:
        return
    _set_paragraph_text(segments.summary_paragraphs[0], summary)
    for paragraph in segments.summary_paragraphs[1:]:
        _set_paragraph_text(paragraph, "")


def _apply_skills(segments: DocxSegments, skills: SkillCategories) -> None:
    if not segments.skills_paragraphs:
        return
    lines = _skills_lines(skills)
    if not lines:
        return
    for index, paragraph in enumerate(segments.skills_paragraphs):
        _set_paragraph_text(paragraph, lines[index] if index < len(lines) else "")


def _apply_jobs(segments: DocxSegments, resume: TailoredResumeContent) -> None:
    for job_index, job_seg in enumerate(segments.jobs):
        if job_index >= len(resume.experience):
            for paragraph in job_seg.header_paragraphs + job_seg.bullet_paragraphs:
                _set_paragraph_text(paragraph, "")
            continue
        job = resume.experience[job_index]
        headers = job_seg.header_paragraphs
        # Preserve multi-line headers (common in Nemanja-style samples):
        # line 1 = "Company | dates", line 2 = job title.
        if len(headers) >= 2:
            company_dates = " | ".join(part for part in (job.company, job.dates) if part)
            _set_paragraph_text(headers[0], company_dates or job.title)
            _set_paragraph_text(headers[1], job.title if company_dates else (job.company or ""))
            for paragraph in headers[2:]:
                _set_paragraph_text(paragraph, "")
        elif len(headers) == 1:
            title_line = " | ".join(part for part in (job.title, job.company, job.dates) if part)
            _set_paragraph_text(headers[0], title_line)
        bullets = [b.strip() for b in job.bullets if b and b.strip()]
        for bullet_index, paragraph in enumerate(job_seg.bullet_paragraphs):
            if bullet_index < len(bullets):
                _set_paragraph_text(paragraph, bullets[bullet_index])
            else:
                _set_paragraph_text(paragraph, "")


def _apply_education(segments: DocxSegments, resume: TailoredResumeContent) -> None:
    if not segments.education_paragraphs or not resume.education:
        return
    lines: list[str] = []
    for edu in resume.education:
        bits = [part for part in (edu.degree, edu.institution, edu.dates) if part]
        if bits:
            lines.append(" | ".join(bits))
    for index, paragraph in enumerate(segments.education_paragraphs):
        _set_paragraph_text(paragraph, lines[index] if index < len(lines) else "")


def fill_docx_template(source_docx: Path, dest_docx: Path, resume: TailoredResumeContent) -> None:
    """Copy source_docx to dest_docx and rewrite summary/skills/jobs/education."""
    dest_docx.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_docx, dest_docx)
    document = Document(str(dest_docx))
    segments = segment_document(document)
    if not segments.is_confident:
        logger.warning(
            "Uploaded template %s could not be segmented confidently; writing best-effort content",
            source_docx,
        )
    _apply_summary(segments, resume.summary)
    _apply_skills(segments, resume.skills)
    _apply_jobs(segments, resume)
    _apply_education(segments, resume)
    document.save(str(dest_docx))
