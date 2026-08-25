"""Deterministic, no-AI post-generation validation — "Step 6" of the pipeline.

Runs right after the OpenAI call to check (and, where safe, auto-correct)
the tailoring rules that must never be violated: company names and
employment dates unchanged from the source CV, the Certifications section
preserved verbatim, the Languages section forced to its fixed value (see
app/core/constants.py - never sourced from the CV or the AI), no duplicated
bullets, the expected bullet count per job, and the Professional Summary's
years of experience matching the CV date span (earliest job start through
latest job end).

Auto-correction *restores an original CV value* (company/dates/
certifications), *forces the one fixed non-CV value* (languages),
*replaces an invented summary year-count with the CV-derived career span*
(see app/services/career_tenure.py), or *removes exact duplicate text* —
it never invents employers, dates, or certifications.

Also home to close_ats_gaps - AGGRESSIVE_MATCH_MODE's deterministic
"regenerate until score >= 95%" safety net (see app/core/config.py's
tailoring_mode docstring). It never calls OpenAI a second time: it only
adds a skill to the Skills section that app/services/resume_matcher.py
already vetted as genuinely matched/transferable (i.e. real or
transferable CV support already established, never invented here) but the
single AI call happened to omit from the Skills list specifically, and
strips unprofessional "Matched skills:" / "Transferable:" dumps from the
Professional Summary.

Also home to bullets_missing_metrics - a lightweight, no-AI check used to
decide whether ai_tailor.tailor_resume's refinement loop needs to ask the
model for stronger quantified impact (every bullet should carry a number),
per the project rule that experience bullets must include measurable data
wherever the underlying work supports a reasonable figure.
"""
import re

from app.core.constants import EXPERIENCE_BULLET_COUNT, FIXED_LANGUAGES_SECTION
from app.models.schemas import (
    MasterCvData,
    ResumeMatch,
    SkillCategories,
    TailoredResumeContent,
    ValidationReport,
)
from app.services.career_tenure import apply_career_years_to_summary, career_tenure_phrase
from app.services.jd_analyzer import (
    _AI_ML_TOOLS,
    _CLOUD_PLATFORMS,
    _DATABASES,
    _DEVOPS_TOOLS,
    _FRAMEWORKS,
    _METHODOLOGIES,
    _PROGRAMMING_LANGUAGES,
    _TECHNOLOGY_TERMS,
    _term_present,
)

# The subset of _FRAMEWORKS that's specifically front-end (the rest of
# _FRAMEWORKS - Django, Flask, FastAPI, Spring, etc - is backend). Used only
# to route a skill into SkillCategories.frontend vs .backend in
# close_ats_gaps below; jd_analyzer.py doesn't need this split since it
# just needs "is this a framework at all", but SkillCategories does.
_FRONTEND_FRAMEWORKS = {
    "react", "angular", "vue", "nextjs", "nuxt", "svelte", "ember", "backbone", "gatsby", "remix",
}


def _experience_for_tenure(tailored: TailoredResumeContent, master_cv: MasterCvData):
    """Prefer master-CV dates; fall back to tailored jobs on the unstructured path."""
    return master_cv.experience or tailored.experience


def _apply_career_tenure(
    tailored: TailoredResumeContent,
    master_cv: MasterCvData,
    issues: list[str],
) -> None:
    """Overwrite an invented summary year-count with the CV date span."""
    experience = _experience_for_tenure(tailored, master_cv)
    updated = apply_career_years_to_summary(tailored.summary, experience)
    if updated == (tailored.summary or ""):
        return
    phrase = career_tenure_phrase(experience)
    if phrase:
        issues.append(
            f"Summary: years of experience set to {phrase} "
            "(earliest job start through latest job end)"
        )
    tailored.summary = updated


def validate_and_fix_resume(
    tailored: TailoredResumeContent,
    master_cv: MasterCvData,
    bullets_per_job: list[int] | None,
) -> ValidationReport:
    """Mutates `tailored` in place to auto-correct any drift found, and
    returns a report of what was checked/fixed.

    bullets_per_job (the master CV's own original per-job bullet counts)
    is accepted for signature stability but no longer drives the expected
    bullet count below - every job must have exactly EXPERIENCE_BULLET_COUNT
    bullets, regenerated for the JD, regardless of the master's original
    count (see app/core/constants.py)."""
    issues: list[str] = []
    del bullets_per_job

    if master_cv.is_structured and len(master_cv.experience) == len(tailored.experience):
        for i, (original, generated) in enumerate(zip(master_cv.experience, tailored.experience)):
            if original.company and generated.company.strip() != original.company.strip():
                issues.append(f"job #{i + 1}: company name drifted ({generated.company!r}) - restored to {original.company!r}")
                generated.company = original.company
            if original.dates and generated.dates.strip() != original.dates.strip():
                issues.append(f"job #{i + 1}: employment dates drifted ({generated.dates!r}) - restored to {original.dates!r}")
                generated.dates = original.dates

    # Languages: a FIXED, backend-only section (see app/core/constants.py) -
    # never read from the master CV, never AI-generated, in EITHER the
    # structured or fallback path. Force it unconditionally so no path (a
    # fallback-mode AI slip, a future code change, etc.) can ever surface
    # anything else here.
    if tailored.languages != FIXED_LANGUAGES_SECTION:
        issues.append(f"Languages section normalized to the fixed value: {FIXED_LANGUAGES_SECTION}")
        tailored.languages = list(FIXED_LANGUAGES_SECTION)

    # Certifications: in the structured path this is always spliced
    # verbatim by ai_tailor._assemble_full_resume and can't drift, but the
    # fallback raw-text path has the AI produce this field itself (see
    # RESUME_TAILOR_SYSTEM_PROMPT) - so if the source CV had a non-empty
    # section and the model dropped or altered it, restore the original
    # verbatim rather than silently losing it.
    if master_cv.is_structured:
        if master_cv.certifications_raw and tailored.certifications != master_cv.certifications_raw:
            issues.append("Certifications section drifted from the master CV - restored verbatim")
            tailored.certifications = list(master_cv.certifications_raw)
    else:
        # Fallback path: we don't have a deterministic source of truth to
        # restore from (raw_text isn't segmented), so just flag it if the
        # model produced nothing but the raw text plausibly had a
        # Certifications heading - a human-visible signal rather than a
        # silent loss.
        lower_raw = master_cv.raw_text.lower()
        if not tailored.certifications and ("certif" in lower_raw or "license" in lower_raw):
            issues.append("Master CV appears to mention certifications, but none were preserved in the tailored output - please verify")

    for i, entry in enumerate(tailored.experience):
        expected = EXPERIENCE_BULLET_COUNT

        deduped: list[str] = []
        seen: set[str] = set()
        for bullet in entry.bullets:
            key = " ".join(bullet.strip().lower().split())
            if key in seen:
                issues.append(f"job #{i + 1}: removed duplicate bullet")
                continue
            seen.add(key)
            deduped.append(bullet)
        entry.bullets = deduped

        if len(entry.bullets) != expected:
            issues.append(f"job #{i + 1}: expected {expected} bullets, got {len(entry.bullets)}")

    _apply_career_tenure(tailored, master_cv, issues)

    return ValidationReport(issues=issues)


# Any digit at all counts as "has a quantifiable metric" - %, counts, time
# saved, scale (users/requests/records/TPS), cost, uptime, team size, and
# multipliers ("2x", "10x") all contain a digit; this deliberately doesn't
# try to distinguish a "good" metric from a weak one (e.g. a year in a
# version number) - it's a cheap, no-AI signal to catch the common failure
# mode of a bullet with NO number anywhere, which prompt strengthening
# alone doesn't reliably prevent.
_METRIC_PATTERN = re.compile(r"\d")


def bullets_missing_metrics(resume: TailoredResumeContent) -> list[str]:
    """Return every experience bullet with no digit anywhere in it - i.e. no
    percentage, count, timeframe, or scale figure. Used by
    ai_tailor.tailor_resume to decide whether to spend a refinement pass
    asking the model to quantify these specific bullets (using the CV's
    real figure when available, otherwise a reasonable, conservative
    estimate consistent with that job's actual described scope - never an
    invented, implausible number), rather than leaving weak, unquantified
    bullets in the final resume."""
    return [bullet for entry in resume.experience for bullet in entry.bullets if not _METRIC_PATTERN.search(bullet)]


def _best_skill_category(term: str) -> str | None:
    """Best-guess SkillCategories field for a bare skill term, reusing the
    same curated category vocabularies jd_analyzer.py uses to parse the JD
    (keeps categorization consistent across the app).

    Returns None - meaning "don't add this to Skills at all" - for anything
    not in jd_analyzer._TECHNOLOGY_TERMS. This gate matters: resume_match's
    matched_skills/transferable_skills are sourced (via
    resume_matcher._collect_jd_terms) partly from generic keyword extraction
    over the JD's free-text requirement lines (e.g. "Bachelor's degree",
    "excellent written communication") - great for ATS keyword-overlap
    *scoring*, but "business"/"write"/"quality"/"issues" are NOT real named
    technologies and must never end up sitting in the Skills section. Only
    genuine tools/languages/frameworks/platforms are ever added here."""
    lower = term.lower().strip()
    if lower in _PROGRAMMING_LANGUAGES:
        return "languages"
    if lower in _FRONTEND_FRAMEWORKS:
        return "frontend"
    if lower in _FRAMEWORKS:
        return "backend"
    if lower in _CLOUD_PLATFORMS:
        return "cloud"
    if lower in _DEVOPS_TOOLS:
        return "devops"
    if lower in _DATABASES:
        return "databases"
    if lower in _AI_ML_TOOLS:
        return "ai"
    # Methodologies / practices (Agile, CI/CD, etc.) — JD nice-to-haves often
    # land here; put them in tools so preferred coverage is visible.
    if lower in _METHODOLOGIES:
        return "tools"
    if lower in _TECHNOLOGY_TERMS:
        return "tools"
    return None


def _match_skill_terms(resume_match: ResumeMatch) -> list[str]:
    """Flatten matched + transferable JD terms (transferable entries are
    stored as 'term (related: existing_skill)' in resume_matcher)."""
    terms: list[str] = list(resume_match.matched_skills)
    for entry in resume_match.transferable_skills:
        term = entry.split(" (related:")[0].strip()
        if term:
            terms.append(term)
    return terms


# Well-known acronyms/initialisms that read wrong with only their first
# letter capitalized (e.g. "Ci/cd", "Api") - consulted ONLY as a fallback
# for a JD-matched term with no exact spelling on the master CV itself
# (see _skill_display_form); a term the CV actually lists always wins via
# cv_casing instead, per-candidate CV wording is never overridden here.
_KNOWN_ACRONYMS = {
    "ci/cd", "api", "apis", "sql", "nosql", "aws", "gcp", "sso", "jwt", "rest",
    "grpc", "saas", "paas", "iaas", "ui", "ux", "css", "html", "xml", "json",
    "yaml", "sdk", "cli", "orm", "crud", "tdd", "bdd", "oop", "mvc", "seo",
    "ai", "ml", "nlp", "llm", "etl", "vpc", "iam", "cdn", "dns", "http", "https",
}


def _skill_display_form(term: str, cv_casing: dict[str, str]) -> str:
    """Render a skill term the way the master CV itself writes it, not
    whatever casing it happened to arrive in.

    matched_skills/transferable_skills come from jd_analyzer's own
    normalized (all-lowercase) technology vocabulary, while
    master_cv.skills_raw preserves the CV's original spelling (e.g.
    "TypeScript", "GitHub Actions", "CI/CD"). Without this, a term
    matched via the JD path renders in jd_analyzer's flat-lowercase form
    while an unmatched CV-only term keeps its proper casing, producing an
    inconsistent, unprofessional-looking mix on the same line. Preferring
    cv_casing here means every skill that genuinely appears on the master
    CV is always shown exactly as the candidate wrote it, regardless of
    which code path first surfaced it.

    Falls back to capitalizing just the first character (leaving the rest
    untouched, so acronym-style casing already present - e.g. "iOS" -
    isn't mangled) for the rare JD term that matched only via a keyword
    stem in prose and never appears in skills_raw verbatim.
    """
    lower = term.lower().strip()
    exact = cv_casing.get(lower)
    if exact:
        return exact
    if lower in _KNOWN_ACRONYMS:
        return lower.upper()
    term = term.strip()
    return term[:1].upper() + term[1:] if term else term


def normalize_ai_skills(skills: SkillCategories, master_cv: MasterCvData) -> SkillCategories:
    """Light, no-AI cleanup pass over the AI-generated Skills section.

    The AI is deliberately free to add any JD-relevant skill, including
    ones not present on the master CV (see the current tailoring policy in
    app/prompts/resume_tailor_prompt.py) - this function does NOT restrict
    which skills may appear. It only:
    1. Dedupes case-insensitively across all categories (keeps the first
       occurrence's category if the model listed the same term twice).
    2. Renders each term in the master CV's own spelling when it happens to
       appear there (see _skill_display_form), otherwise applies
       consistent capitalization/acronym casing - so a real CV skill and
       an AI-added one never look inconsistently cased side by side.
    """
    cv_casing = {token.lower(): token for token in master_cv.skills_raw}
    seen: set[str] = set()
    normalized = SkillCategories()
    for category in SkillCategories.model_fields:
        bucket = getattr(normalized, category)
        for term in getattr(skills, category):
            lower = term.lower().strip()
            if not lower or lower in seen:
                continue
            seen.add(lower)
            bucket.append(_skill_display_form(term, cv_casing))
    return normalized


def _sanitize_summary_prose(summary: str) -> str:
    """Strip ATS keyword-dump tails the model sometimes appends.

    Removes trailing clauses like "Matched skills: …", "Transferable: …",
    or "Hands-on with a, b, c." so the Professional Summary stays readable
    prose. Skills coverage for ATS lives in the Skills section + bullets.
    """
    text = (summary or "").strip()
    if not text:
        return text

    dump = re.compile(
        r"(?is)\s+(?:"
        r"Matched(?:\s+skills|\s+terms)?\s*:|"
        r"Transferable(?:\s+skills)?\s*:|"
        r"Transferable experience with\b|"
        r"Hands-on with\b"
        r").*$"
    )
    cleaned = dump.sub("", text).rstrip(" ;,")
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _preferred_terms_for_summary(resume_match: ResumeMatch) -> list[str]:
    """Preferred / nice-to-have JD terms the CV supports (display form)."""
    terms: list[str] = list(resume_match.preferred_matched)
    for entry in resume_match.preferred_transferable:
        term = entry.split(" (related:")[0].strip()
        if term:
            terms.append(term)
    # Dedupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def _weave_preferred_into_summary(summary: str, preferred_terms: list[str], *, max_terms: int = 8) -> tuple[str, list[str]]:
    """Ensure CV-supported preferred skills appear in the summary as prose.

    If the model omitted nice-to-haves, append one natural sentence naming
    the missing ones — never 'Matched skills:' dumps.
    """
    text = _sanitize_summary_prose(summary)
    if not preferred_terms:
        return text, []
    lower = text.lower()
    missing = [t for t in preferred_terms if t and not _term_present(t.lower(), lower)]
    if not missing:
        return text, []
    to_add = missing[:max_terms]
    if len(to_add) == 1:
        sentence = f"Additional strengths include {to_add[0]}, aligned with this role's preferred qualifications."
    elif len(to_add) == 2:
        sentence = (
            f"Additional strengths include {to_add[0]} and {to_add[1]}, "
            "aligned with this role's preferred qualifications."
        )
    else:
        head = ", ".join(to_add[:-1])
        sentence = (
            f"Additional strengths include {head}, and {to_add[-1]}, "
            "aligned with this role's preferred qualifications."
        )
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return f"{text} {sentence}".strip(), to_add


def close_ats_gaps(tailored: TailoredResumeContent, resume_match: ResumeMatch, master_cv: MasterCvData) -> list[str]:
    """Deterministic (no second OpenAI call) ATS safety net for
    AGGRESSIVE_MATCH_MODE.

    1. Tops up Skills with every matched/transferable named technology the
       single AI call omitted (preferred/nice-to-have terms first).
    2. Sanitizes the Professional Summary and weaves any omitted preferred
       CV-supported terms into one professional closing sentence.

    resume_matcher already vetted every candidate term as genuinely
    supported by the CV (direct or transferable). Mutates `tailored` in
    place. Returns human-readable notes for the validation/perf report.
    """
    issues: list[str] = []
    # Preferred first, then the full matched/transferable set.
    preferred = _preferred_terms_for_summary(resume_match)
    candidates = list(dict.fromkeys(preferred + _match_skill_terms(resume_match)))
    cv_casing = {token.lower(): token for token in master_cv.skills_raw}

    existing_text = " ".join(
        " ".join(group)
        for group in (
            tailored.skills.languages,
            tailored.skills.backend,
            tailored.skills.frontend,
            tailored.skills.cloud,
            tailored.skills.devops,
            tailored.skills.databases,
            tailored.skills.ai,
            tailored.skills.tools,
        )
    ).lower()

    added: set[str] = set()
    for term in candidates:
        lower = term.lower().strip()
        if not lower or lower in added or _term_present(lower, existing_text):
            continue
        category = _best_skill_category(term)
        if category is None:
            continue
        display = _skill_display_form(term, cv_casing)
        getattr(tailored.skills, category).append(display)
        existing_text += f" {lower}"
        added.add(lower)
        kind = "preferred" if term in preferred or any(
            term.lower() == p.lower() for p in preferred
        ) else "matched/transferable"
        issues.append(
            f"Skills: added '{term}' ({category}, {kind}) - CV-supported, "
            "omitted from the Skills section"
        )

    cleaned = _sanitize_summary_prose(tailored.summary)
    if cleaned != (tailored.summary or "").strip():
        issues.append("Summary: removed ATS keyword-dump labels for professional prose")

    woven, injected = _weave_preferred_into_summary(cleaned, preferred)
    if injected:
        issues.append(
            "Summary: wove preferred/nice-to-have terms into prose: " + ", ".join(injected)
        )
    tailored.summary = woven
    # close_ats_gaps rewrites the summary after validate_and_fix_resume, so
    # re-apply CV-derived years here as the last summary mutation.
    _apply_career_tenure(tailored, master_cv, issues)

    return issues
