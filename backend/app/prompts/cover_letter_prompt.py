"""Prompt templates for job-application cover letters.

Kept separate from app/services/ai_cover_letter.py so prompt text can be
reviewed without touching the OpenAI-calling logic. See
.cursor/rules/resume-tailor-code-standards.mdc.
"""
from app.models.schemas import JdAnalysis, TailoredResumeContent

COVER_LETTER_SYSTEM_PROMPT = """\
Write a professional job-application cover letter. Output ONLY greeting, \
3-4 body paragraphs, and a closing line (e.g. Sincerely,). Do not include \
a sender address, date, recipient address, or the candidate's name after \
the closing - the backend adds those.

IDENTITY FACTS: use only the candidate's name, employers, dates, titles, \
education, and skills given in the user message. Never invent employers, \
degrees, certifications, tools, or metrics that are not in the tailored \
resume. Do not copy resume bullets verbatim; paraphrase into letter prose.

TONE: confident, specific, one page. Paragraph 1: the target role and \
company, and why this candidate. Middle paragraphs: strongest resume \
evidence matched to the job description's required and preferred skills. \
Final paragraph: genuine interest and readiness to discuss the role.
"""


def _skill_digest(resume: TailoredResumeContent, limit: int = 18) -> str:
    groups = (
        resume.skills.languages,
        resume.skills.backend,
        resume.skills.frontend,
        resume.skills.cloud,
        resume.skills.devops,
        resume.skills.databases,
        resume.skills.ai,
        resume.skills.tools,
    )
    skills: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for skill in group:
            key = skill.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            skills.append(skill)
            if len(skills) >= limit:
                return ", ".join(skills)
    return ", ".join(skills) or "(none listed)"


def _job_digest(resume: TailoredResumeContent, jobs: int = 3, bullets_each: int = 3) -> str:
    blocks: list[str] = []
    for entry in resume.experience[:jobs]:
        bullet_lines = "\n".join(f"  - {b}" for b in entry.bullets[:bullets_each])
        blocks.append(
            f'{entry.title} at {entry.company} ({entry.dates})\n{bullet_lines}'
        )
    return "\n\n".join(blocks) or "(no experience listed)"


def build_cover_letter_user_message(
    resume: TailoredResumeContent,
    jd_analysis: JdAnalysis,
    job_description: str,
    company_name: str,
) -> str:
    """Compact prompt from the tailored resume + JD. Identity facts stay
    verbatim from the resume; the letter is written to this company/role."""
    role = jd_analysis.target_job_title or "the advertised role"
    required = ", ".join(jd_analysis.required_skills[:12]) or "(none parsed)"
    preferred = ", ".join(jd_analysis.preferred_skills[:10]) or "(none parsed)"
    jd_clip = job_description.strip()
    if len(jd_clip) > 1800:
        jd_clip = jd_clip[:1800] + "\n...(truncated)"

    education = "; ".join(
        f"{e.degree} — {e.institution} ({e.dates})" for e in resume.education[:3]
    ) or "(none listed)"

    return (
        f"TARGET COMPANY: {company_name.strip()}\n"
        f"TARGET ROLE: {role}\n"
        f"REQUIRED SKILLS: {required}\n"
        f"PREFERRED SKILLS: {preferred}\n\n"
        f"CANDIDATE: {resume.contact.name}\n"
        f"PROFESSIONAL SUMMARY:\n{resume.summary.strip()}\n\n"
        f"RECENT EXPERIENCE (identity facts — do not alter employers/dates):\n"
        f"{_job_digest(resume)}\n\n"
        f"SKILLS: {_skill_digest(resume)}\n"
        f"EDUCATION: {education}\n\n"
        f"JOB DESCRIPTION:\n{jd_clip}\n\n"
        "Write the cover letter now. 3-4 paragraphs. Ground every claim in "
        "the tailored resume above."
    )
