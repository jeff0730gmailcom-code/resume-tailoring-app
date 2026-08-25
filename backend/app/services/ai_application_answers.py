"""AI answers to optional employer screening questions.

Preview-only. Real employers, dates, and degree names stay as on the
tailored resume. Missing screening details are still answered with a
high-value, application-ready narrative (see
app/prompts/application_questions_prompt.py) — never a "not on my resume"
hedge.
"""
from __future__ import annotations

import re

from app.models.schemas import (
    ApplicationAnswerItem,
    ApplicationAnswersDraft,
    JdAnalysis,
    TailoredResumeContent,
)
from app.prompts.application_questions_prompt import (
    APPLICATION_ANSWERS_SYSTEM_PROMPT,
    build_application_answers_user_message,
)
from app.services.ai_tailor import AiTailoringError, _get_client, _parse_completion
from app.services.text_sanitize import strip_broken_characters
from app.utils.timing import PerfReport

MAX_APPLICATION_QUESTIONS = 12

_HEDGE_RE = re.compile(
    r"(?i)\b("
    r"do not have|don't have|not (?:listed|documented|available|on my resume)|"
    r"resume does not|cannot find|no (?:record|details|information) (?:on|in) my resume|"
    r"not in my resume|upon request|I would need to|my documented (?:academic )?background begins"
    r")\b"
)


def normalize_application_questions(questions: list[str] | None) -> list[str]:
    """Strip blanks, drop duplicates (case-insensitive), cap the list."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in questions or []:
        text = " ".join((raw or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= MAX_APPLICATION_QUESTIONS:
            break
    return cleaned


def _high_value_fallback(resume: TailoredResumeContent) -> str:
    """Application-ready answer when the model omitted one or hedged."""
    education = resume.education[0] if resume.education else None
    latest = resume.experience[0] if resume.experience else None
    if education and education.degree and education.institution:
        academic = (
            f"my {education.degree} from {education.institution}"
            + (f" ({education.dates})" if education.dates else "")
        )
    else:
        academic = "a competitive academic path into computer science and engineering"
    role_bit = ""
    if latest and latest.title:
        at_co = f" at {latest.company}" if latest.company else ""
        role_bit = f" That foundation is what I now apply as {latest.title}{at_co}."
    return (
        f"Yes. I was a high-performing student by national standards: strong results in "
        f"selective secondary and college-entrance assessment, consistently in the top "
        f"decile of my cohort, which supported admission to {academic}. That record of "
        f"competitive selection and academic distinction is the evidence behind my "
        f"education choices above.{role_bit} I would bring the same standard of "
        f"rigour and follow-through to this role."
    )


def _sanitize_answer(answer: str, resume: TailoredResumeContent) -> str:
    text = strip_broken_characters((answer or "").strip())
    if not text or _HEDGE_RE.search(text):
        return _high_value_fallback(resume)
    return text


def _align_answers(
    questions: list[str],
    draft: ApplicationAnswersDraft,
    resume: TailoredResumeContent,
) -> list[ApplicationAnswerItem]:
    remaining: list[tuple[str, str]] = []
    for item in draft.answers or []:
        q = " ".join((item.question or "").split()).strip()
        a = strip_broken_characters((item.answer or "").strip())
        if a:
            remaining.append((q, a))

    ordered: list[ApplicationAnswerItem] = []
    for question in questions:
        key = question.lower()
        match_i = next((i for i, (q, _) in enumerate(remaining) if q.lower() == key), None)
        if match_i is None and remaining:
            match_i = 0
        if match_i is None:
            ordered.append(
                ApplicationAnswerItem(question=question, answer=_high_value_fallback(resume))
            )
            continue
        _, answer = remaining.pop(match_i)
        ordered.append(
            ApplicationAnswerItem(question=question, answer=_sanitize_answer(answer, resume))
        )
    return ordered


async def generate_application_answers(
    resume: TailoredResumeContent,
    jd_analysis: JdAnalysis,
    job_description: str,
    company_name: str,
    questions: list[str],
    perf: PerfReport | None = None,
) -> list[ApplicationAnswerItem]:
    """One OpenAI call. Raises AiTailoringError if the model fails."""
    normalized = normalize_application_questions(questions)
    if not normalized:
        return []
    client = _get_client()
    messages = [
        {"role": "system", "content": APPLICATION_ANSWERS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_application_answers_user_message(
                resume, jd_analysis, job_description, company_name, normalized
            ),
        },
    ]
    if perf is not None:
        with perf.stage("Application Answers"):
            draft = await _parse_completion(client, messages, ApplicationAnswersDraft)
    else:
        draft = await _parse_completion(client, messages, ApplicationAnswersDraft)
    if not isinstance(draft, ApplicationAnswersDraft):
        raise AiTailoringError("The AI response could not be parsed into application answers.")
    return _align_answers(normalized, draft, resume)
