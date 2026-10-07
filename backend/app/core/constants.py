"""App-wide fixed constants that must never be sourced from AI output or
from the candidate's own CV text.

FIXED_LANGUAGES_SECTION backs the "Languages" section rule: it is the
tailored resume's Languages section for every candidate except Sean
(US native — that section is omitted). It is never taken from the source
CV or from AI output. See:
- app/services/ai_tailor.py (_assemble_full_resume) - structured path splice
- app/services/resume_validator.py (validate_and_fix_resume) - forces this
  value for both the structured and fallback (raw-CV-text AI) paths
- app/services/template_renderer.py - renders it into the selected resume
  template
- app/services/ats_scorer.py (_flatten_resume_text) - deliberately NOT
  included in ATS keyword-match text; this section is never part of ATS
  optimization logic.

EXPERIENCE_BULLET_COUNT is the fixed number of bullets every experience
entry must have in the final tailored resume - always regenerated to
target the job description, regardless of how many bullets that job had
on the master CV. Every selectable resume template (see
app/templates/resumes/) has exactly this many fixed bullet slots per job.
See:
- app/prompts/resume_tailor_prompt.py (build_structured_user_message) -
  tells the AI to write exactly this many bullets per job
- app/services/ai_tailor.py (_assemble_full_resume) - pads/trims the AI's
  bullets to this count
- app/services/resume_validator.py (validate_and_fix_resume) - flags any
  job that doesn't end up with exactly this many bullets
"""

FIXED_LANGUAGES_SECTION: list[str] = ["English — C1"]

EXPERIENCE_BULLET_COUNT: int = 8


def spoken_languages_for_candidate(name: str) -> list[str]:
    """Spoken-language lines appended at the end of a tailored resume.

    Sean is a US native, so his resumes omit this section. Every other
    candidate keeps the fixed English — C1 line.
    """
    first = ""
    for token in (name or "").replace(",", " ").split():
        first = token.strip(".").lower()
        if first:
            break
    if first == "sean":
        return []
    return list(FIXED_LANGUAGES_SECTION)
