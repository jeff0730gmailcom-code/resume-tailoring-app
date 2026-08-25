"""AI cover-letter generation from a tailored resume + job description.

Preview-only: this service never renders PDF/DOCX. Identity facts (name,
employers, dates, education) come from the already-tailored resume, not
from the model. Prompt text lives in app/prompts/cover_letter_prompt.py.
"""
from __future__ import annotations

from app.models.schemas import CoverLetterContent, CoverLetterDraft, JdAnalysis, TailoredResumeContent
from app.prompts.cover_letter_prompt import COVER_LETTER_SYSTEM_PROMPT, build_cover_letter_user_message
from app.services.ai_tailor import AiTailoringError, _get_client, _parse_completion
from app.services.text_sanitize import strip_broken_characters
from app.utils.timing import PerfReport


def _assemble_cover_letter(
    draft: CoverLetterDraft,
    resume: TailoredResumeContent,
    company_name: str,
) -> CoverLetterContent:
    paragraphs = [
        strip_broken_characters(p.strip())
        for p in (draft.paragraphs or [])
        if (p or "").strip()
    ]
    greeting = strip_broken_characters((draft.greeting or "").strip()) or "Dear Hiring Manager,"
    closing = strip_broken_characters((draft.closing or "").strip()) or "Sincerely,"
    if not closing.endswith((",", ".")):
        closing = f"{closing},"
    return CoverLetterContent(
        recipient_company=company_name.strip(),
        greeting=greeting,
        paragraphs=paragraphs,
        closing=closing,
        sender_name=resume.contact.name,
        sender_location=resume.contact.location,
        sender_email=resume.contact.email,
        sender_phone=resume.contact.phone,
    )


async def generate_cover_letter(
    resume: TailoredResumeContent,
    jd_analysis: JdAnalysis,
    job_description: str,
    company_name: str,
    perf: PerfReport | None = None,
) -> CoverLetterContent:
    """One OpenAI call. Raises AiTailoringError if the model fails."""
    client = _get_client()
    messages = [
        {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_cover_letter_user_message(
                resume, jd_analysis, job_description, company_name
            ),
        },
    ]
    if perf is not None:
        with perf.stage("Cover Letter"):
            draft = await _parse_completion(client, messages, CoverLetterDraft)
    else:
        draft = await _parse_completion(client, messages, CoverLetterDraft)
    if not isinstance(draft, CoverLetterDraft):
        raise AiTailoringError("The AI response could not be parsed into a cover letter.")
    return _assemble_cover_letter(draft, resume, company_name)
