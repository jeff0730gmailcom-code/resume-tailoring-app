"""Prompt templates for AI resume tailoring.

Kept separate from app/services/ai_tailor.py so prompt text can be reviewed
and iterated on without touching the OpenAI-calling logic. See
.cursor/rules/resume-tailoring-prompt-rules.mdc for the source rules this
prompt implements.

Tailoring policy (current): employer names, employment dates, education,
and certifications are IDENTITY FACTS - always taken verbatim from the
master CV, never AI-authored. Everything else - experience bullets, the
professional summary, and the full Skills list - is generated to best fit
the target job description, NOT limited to what the candidate's real CV
already shows for that specific job/skillset. The AI is explicitly asked to
write JD-driven bullets and a JD-driven skill set (see
app/services/ai_tailor.py's module docstring for the exact split between
what's spliced in verbatim vs. generated).

All prompt text below is deliberately terse - every sentence trimmed to its
substantive content with redundant phrasing/restatement removed. This is a
direct latency lever (fewer input tokens per OpenAI call) as well as a cost
lever. The structured path uses a compact schema (summary + skills +
per-job title/bullets) built from pre-parsed CV/JD data so a single
gpt-4o-mini call stays under the <5s tailor target - see app/core/config.py.
"""
from app.core.constants import EXPERIENCE_BULLET_COUNT
from app.models.schemas import JdAnalysis, MasterCvData, ResumeMatch

RESUME_TAILOR_SYSTEM_PROMPT = """\
Expert resume writer + ATS optimization specialist. Transform a candidate's \
master CV into a resume tailored to a job description, targeting >95% ATS \
match.

IDENTITY FACTS (must stay real, never AI-authored): employers, employment \
dates, education, and certifications must exactly match the source CV - \
never invent, alter, or drop these. Company names/dates carried over \
exactly as in the CV. Only tailor content (wording/emphasis/order), never \
layout/styling.

`languages`: fixed backend-controlled field, always overwritten after you \
respond - leave it an empty list, spend no effort on it.
`certifications`: if the CV has one, copy every line VERBATIM, same order, \
unchanged; empty list only if genuinely absent.

JOB TITLES: may shift to the JD's terminology.

BULLETS (JD-DRIVEN): write exactly the fixed count given in the user \
message for EVERY job (never invent extra jobs). Bullets describe the \
work, tools, and impact a strong candidate for THIS job description would \
have - write them to best match the JD's required and preferred skills/ \
responsibilities. Not limited to, or copied/trimmed from, that job's own \
original CV bullets - fully regenerate every job's bullets around the JD, \
varied across jobs (no repeats), plausible for that job's title/seniority/ \
era. ONE short sentence each (~22 words): Action + tech + impact + a \
NUMBER (mandatory - use the CV's figure when present, else a reasonable \
estimate consistent with that job's scope/seniority).

SUMMARY: fully fresh professional prose, 3-4 sentences (never a keyword \
dump). Sentence 1: JD job title + years of experience. Sentence 2-3: \
strongest required AND preferred/nice-to-have technologies for this role. \
Final sentence: one measurable impact. NEVER write labels like "Matched \
skills:", "Matched terms:", "Transferable:", or comma-lists of keywords — \
every skill name must appear inside normal sentences.

SKILLS: build the most complete, JD-relevant skill set you can across all \
categories (languages, backend, frontend, cloud, devops, databases, ai, \
tools) - JD-required skills first, then preferred/nice-to-have, then any \
other skill genuinely useful for this role. Not limited to the \
candidate's own CV - add any skill relevant to succeeding in this JD. \
Dedupe; no meta text.

ATS ALIGNMENT: every skill you place in Skills should also be echoed at \
least once in the summary or a bullet, ideally using the JD's own wording \
- ATS scanners match literal text, not synonyms.
"""


def build_user_message(
    cv_text: str, job_description: str, bullets_per_job: list[int] | None = None
) -> str:
    """Build the user-turn message combining the CV and target job description.

    Used only for the rare unstructured fallback path. Truncates input so
    this path cannot recreate the 15s+ full-document generation that blew
    the <5s target. Prefer the structured path.

    Every job gets EXACTLY EXPERIENCE_BULLET_COUNT bullets, fully generated
    to target this JD - never capped by (or copied from) that job's own
    original bullet count. Mirrors build_structured_user_message's policy
    so the fallback path can never under-serve a job just because this is
    the less-common code path.
    """
    del bullets_per_job  # every job always targets the same fixed count now
    count = EXPERIENCE_BULLET_COUNT
    bullet_override = (
        f"\n\nBULLETS: EVERY job gets exactly {count} bullets, fully generated to target this "
        "JD (not limited to, or copied/trimmed from, the CV's own original bullets for that "
        "job). One sentence each (~22 words) + a number."
    )

    cv_clip = cv_text if len(cv_text) <= 2800 else cv_text[:2800] + "\n...(truncated)"
    jd_clip = job_description if len(job_description) <= 2200 else job_description[:2200] + "\n...(truncated)"

    return (
        f"MASTER CV:\n{cv_clip}\n\n"
        f"TARGET JOB DESCRIPTION:\n{jd_clip}"
        f"{bullet_override}\n\n"
        "Produce the tailored resume now. Summary: 3-4 professional prose "
        "sentences (no 'Matched skills' / 'Transferable' labels). Skills: fill every category "
        "with every JD-relevant skill you can, required and preferred first, plus any other "
        "fitting skill - do not leave it sparse."
    )


RESUME_TAILOR_DYNAMIC_SYSTEM_PROMPT = """\
Expert resume writer + ATS specialist. Output ONLY: a professional summary, \
a full skills list, and per-job title/bullets. Contact/education/company \
names/dates/languages/certifications are filled by the backend from the \
candidate's real CV - do not output them.

IDENTITY FACTS: company names, employment dates, and (if you suggest one) \
job titles are context only - the backend always keeps the master CV's \
real company/dates, and its real job title, in the final output regardless \
of what you write here.

BULLETS (JD-DRIVEN): write exactly the fixed count per job given below for \
EVERY job. Bullets describe the work, tools, and impact a strong candidate \
for THIS job description would have - write them to best match the JD's \
required and preferred skills/responsibilities. Not limited to that job's \
real original duties - fully generate every job's bullets around the JD, \
varied across jobs (no repeats), plausible for that job's title/seniority/ \
era. ONE sentence each, max ~22 words. Shape: Action + tech + impact + a \
NUMBER (mandatory - a reasonable estimate consistent with that job's scope/ \
seniority). No filler.

SKILLS: build the most complete, JD-relevant skill set you can across all \
categories (languages, backend, frontend, cloud, devops, databases, ai, \
tools) - JD-required skills first, then preferred/nice-to-have, then any \
other skill genuinely useful for this role. Not limited to the \
candidate's own CV context given below - add any skill relevant to \
succeeding in this JD. Dedupe; no meta text.

SUMMARY: strong professional summary, 3-4 full sentences of prose only. \
Lead with the JD title and years, develop core required + preferred tech \
strengths in the middle, close with measurable impact. Skill names belong \
inside those sentences — never as a trailing "Matched skills / \
Transferable" list.

TITLES: you may suggest a JD-aligned title, but the backend always uses \
the master CV's own original job title in the final output - your \
suggestion is never shown.
"""

# Appended to RESUME_TAILOR_DYNAMIC_SYSTEM_PROMPT only when
# settings.tailoring_mode == "aggressive". Turns up how hard the model
# pushes JD alignment in bullets/skills/summary - the IDENTITY FACTS rule
# above (real company/dates/title) is never relaxed by any mode.
AGGRESSIVE_MODE_ADDENDUM = """

AGGRESSIVE MODE - MAXIMIZE ATS MATCH: every required and preferred JD skill \
must land in skills + summary + >=1 bullet, not just a passing mention. \
Write bullets as if the candidate's whole career was built around this JD. \
Rewrite the summary to lead with the JD's own job-title terminology and top \
2-3 required qualifications. Put ALL JD-relevant skills first in each \
category. Weight the most recent job's bullets heaviest, but keep every \
job's bullets fully JD-driven and non-repetitive.
"""


# Appended instead of AGGRESSIVE_MODE_ADDENDUM when settings.tailoring_mode
# == "aggressive_match" (the strongest intensity available). Any ATS gap
# this mode still leaves after generation is closed deterministically, not
# with a second OpenAI call - see resume_validator.close_ats_gaps.
AGGRESSIVE_MATCH_MODE_ADDENDUM = """

AGGRESSIVE MATCH (target >95% ATS): write summary, skills, and bullets as \
if the role were custom-built for this JD. Prefer JD terminology in \
titles. Include every JD required AND preferred/nice-to-have skill in the \
skills list, and weave the most important ones into the summary and \
bullets as prose (no meta labels).
"""


def get_dynamic_system_prompt(mode: str = "accurate") -> str:
    """Return the system prompt for the structured/dynamic-content path,
    optionally intensified for settings.tailoring_mode == "aggressive" (see
    AGGRESSIVE_MODE_ADDENDUM) or "aggressive_match" (AGGRESSIVE_MATCH_MODE -
    see AGGRESSIVE_MATCH_MODE_ADDENDUM, the strongest intensity) - all three
    modes generate bullets/skills/summary fully around the JD; only the
    IDENTITY FACTS (real company/dates/title) are never AI-authored,
    regardless of mode."""
    if mode == "aggressive_match":
        return RESUME_TAILOR_DYNAMIC_SYSTEM_PROMPT + AGGRESSIVE_MATCH_MODE_ADDENDUM
    if mode == "aggressive":
        return RESUME_TAILOR_DYNAMIC_SYSTEM_PROMPT + AGGRESSIVE_MODE_ADDENDUM
    return RESUME_TAILOR_DYNAMIC_SYSTEM_PROMPT


def build_structured_user_message(
    master_cv: MasterCvData,
    jd_analysis: JdAnalysis,
    resume_match: ResumeMatch,
    job_description: str,
    bullets_per_job: list[int] | None = None,
    mode: str = "accurate",
) -> str:
    """Build a compact prompt from pre-parsed structured CV/JD data (see
    app/services/cv_structurer.py, jd_analyzer.py) instead of sending the
    whole raw CV/JD text - smaller input, faster call.

    Job entries are given only as title/company/dates context (never their
    original bullets) - bullets are meant to be fully regenerated around
    the JD rather than lightly reworded from what that job's real duties
    were, so the original bullet text is deliberately withheld to avoid
    anchoring the model on it.

    resume_match/bullets_per_job are accepted for call-site signature
    stability but no longer constrain skill selection - skills are now
    freely generated from the JD (see RESUME_TAILOR_DYNAMIC_SYSTEM_PROMPT),
    not limited to resume_match's CV-supported terms.

    Falls back to including the raw job_description only if the JD's
    heuristic section-parsing found nothing usable (unusual JD formatting
    with no recognizable requirements/preferred/responsibilities headings) -
    never silently tailors against less information than the old raw-text
    prompt had.
    """
    del resume_match, bullets_per_job

    jobs_desc = []
    for i, entry in enumerate(master_cv.experience):
        jobs_desc.append(
            f'Job #{i + 1}: title "{entry.title}" at "{entry.company}" ({entry.dates}) - write '
            f"exactly {EXPERIENCE_BULLET_COUNT} bullets, fully generated to best match the target "
            "JD below (not this job's own real duties); keep them plausible for this title/era "
            "and distinct from every other job's bullets."
        )
    jobs_block = "\n\n".join(jobs_desc)

    has_parsed_jd = bool(jd_analysis.required_skills or jd_analysis.preferred_skills or jd_analysis.responsibilities)
    if has_parsed_jd:
        # Keep JD block tight - responsibilities capped to cut prompt tokens.
        responsibilities = jd_analysis.responsibilities[:8]
        jd_block = (
            f"TARGET ROLE: {jd_analysis.target_job_title or 'Not specified'}"
            f" | Seniority: {jd_analysis.seniority or 'Not specified'}"
            f" | Domain: {jd_analysis.business_domain or 'Not specified'}\n"
            f"REQUIRED SKILLS: {', '.join(jd_analysis.required_skills) or '(none)'}\n"
            f"PREFERRED SKILLS: {', '.join(jd_analysis.preferred_skills) or '(none)'}\n"
            f"KEY RESPONSIBILITIES: {', '.join(responsibilities) or '(none)'}\n"
            f"PRACTICES: {', '.join(jd_analysis.methodologies) or '(none)'}\n"
        )
    else:
        # Raw JD fallback - truncate extreme postings to protect latency.
        raw = job_description if len(job_description) <= 3500 else job_description[:3500] + "\n...(truncated)"
        jd_block = f"TARGET JOB DESCRIPTION:\n{raw}\n"

    if mode == "aggressive_match":
        mode_note = "MODE: aggressive_match - target >95% ATS, maximize JD alignment.\n\n"
    elif mode == "aggressive":
        mode_note = "MODE: aggressive - apply AGGRESSIVE MODE rules.\n\n"
    else:
        mode_note = ""

    return (
        f"{mode_note}"
        f"CANDIDATE JOBS (titles/companies/dates are fixed context - write bullets only):\n{jobs_block}\n\n"
        f"{jd_block}\n"
        "Produce a tailored summary, a full JD-relevant skills list, and per-job bullets now. "
        "Skills should cover every required + preferred JD skill plus any other skill genuinely "
        "relevant to this role - not limited to the candidate's own CV. Summary: 3-4 professional "
        "prose sentences, no meta labels. Exact bullet counts above, fully JD-driven per job, no "
        "repeats across jobs."
    )


def _weak_bullets_block(weak_bullets: list[str] | None) -> str:
    """Shared instruction block asking the model to add a quantifiable
    metric to specific bullets that came back with none (see
    resume_validator.bullets_missing_metrics) - used by both refinement
    message builders below."""
    if not weak_bullets:
        return ""
    quoted = "\n".join(f'  - "{b}"' for b in weak_bullets)
    return (
        "\nThese bullets have no quantifiable metric - add one to each (a reasonable estimate "
        "consistent with that job's scope/seniority; never an implausible figure):\n"
        f"{quoted}\n"
    )


def build_dynamic_refinement_message(
    missing_keywords: list[str], mode: str = "accurate", weak_bullets: list[str] | None = None
) -> str:
    """Refinement follow-up for the structured/dynamic-content path (see
    build_structured_user_message) - never mentions company/dates since the
    AI never produces those in this path.

    weak_bullets, when non-empty, are bullets from the previous pass with
    no number anywhere (see resume_validator.bullets_missing_metrics) -
    included so the model targets exactly those bullets instead of
    re-guessing which ones need a metric."""
    keyword_list = ", ".join(missing_keywords)
    keyword_block = (
        f"ATS scan: still missing these JD keywords: {keyword_list}.\n"
        "Add each directly to Skills (and echo the most important ones in the summary or a "
        "bullet) - skills are not limited to the candidate's CV, add whatever is JD-relevant.\n"
        if missing_keywords
        else ""
    )
    return (
        f"{keyword_block}"
        f"{_weak_bullets_block(weak_bullets)}"
        "\nRevise now. Keep the exact bullet count per job from before. Output the complete revised summary, "
        "skills, and experience."
    )


def build_refinement_message(missing_keywords: list[str], weak_bullets: list[str] | None = None) -> str:
    """Build a follow-up user-turn message asking the model to close ATS
    keyword gaps (and/or add missing metrics - see weak_bullets) in the
    resume it just produced, given the previous turn's resume JSON is
    already in the conversation as the prior assistant reply."""
    keyword_list = ", ".join(missing_keywords)
    keyword_block = (
        f"ATS scan: still missing these JD keywords: {keyword_list}.\n"
        "Add each directly to Skills (and echo the most important ones in the summary or a "
        "bullet) - skills are not limited to the candidate's CV, add whatever is JD-relevant.\n"
        if missing_keywords
        else ""
    )
    return (
        f"{keyword_block}"
        f"{_weak_bullets_block(weak_bullets)}"
        "\nRevise now applying the above. Keep every other system-prompt rule (exactly 8 bullets per company, "
        "unchanged company names/dates). Output the complete revised resume."
    )
