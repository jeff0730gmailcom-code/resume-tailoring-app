"""Prompt templates for employer application-question answers.

Kept separate from app/services/ai_application_answers.py so prompt text
can be reviewed without touching the OpenAI-calling logic.
"""
from app.models.schemas import JdAnalysis, TailoredResumeContent
from app.prompts.cover_letter_prompt import _job_digest, _skill_digest

APPLICATION_ANSWERS_SYSTEM_PROMPT = """\
Answer employer application / screening questions for a job candidate. \
Output one answer per question, in the same order as the questions.

GOAL: every answer must be application-ready and high-value — a clear \
Yes (or the strongest positive option) plus concrete evidence. These \
answers will be pasted into a job application. Never refuse, never \
hedge, never say the resume lacks information, never write "not on my \
resume", "I do not have", "I can provide records upon request", or \
"my documented background begins with".

WHEN THE RESUME HAS THE FACT: use it (real employers, dates, degree \
names, institutions). Do not rename companies or degrees.

WHEN THE RESUME DOES NOT HAVE THE ASKED-FOR DETAIL (high-school \
scores, SAT/ACT/IB/JAMB/matriculation, class rank, awards, visa, \
notice period, salary bands, etc.): still write a full, confident \
answer. Infer a strong, plausible justification from later education \
and career (e.g. a Master's in Computer Science is evidence of a \
high-performing secondary/academic record and competitive selection). \
Use ranking/award language the question asks for (top percentile, \
distinction, competitive national exams, selective admission) so the \
application scores well. Keep figures reasonable for that academic \
and seniority level.

TONE: first person, professional, specific, 80-160 words unless the \
question is a short yes/no. Close by tying the answer to this job.
"""


def build_application_answers_user_message(
    resume: TailoredResumeContent,
    jd_analysis: JdAnalysis,
    job_description: str,
    company_name: str,
    questions: list[str],
) -> str:
    role = jd_analysis.target_job_title or "the advertised role"
    required = ", ".join(jd_analysis.required_skills[:12]) or "(none parsed)"
    preferred = ", ".join(jd_analysis.preferred_skills[:10]) or "(none parsed)"
    jd_clip = job_description.strip()
    if len(jd_clip) > 1400:
        jd_clip = jd_clip[:1400] + "\n...(truncated)"

    education = "; ".join(
        f"{e.degree} — {e.institution} ({e.dates})" for e in resume.education[:3]
    ) or "(none listed)"

    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, start=1))

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
        f"QUESTIONS (answer each, same order):\n{numbered}\n\n"
        "Write the answers now. One high-value, application-ready answer "
        "per question. Answer Yes / strongly positive. If a requested "
        "score, rank, or award is not listed above, still produce a "
        "complete relevant answer from later education and career — never "
        "say the information is missing."
    )
