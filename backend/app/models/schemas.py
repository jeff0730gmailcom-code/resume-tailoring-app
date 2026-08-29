"""Pydantic schemas shared across the API."""
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    message: str


class ExperienceEntry(BaseModel):
    title: str = Field(description="Job title (may be reframed to match the target role, without inflating seniority)")
    company: str = Field(description="Employer / company name - must match the source CV exactly, never altered")
    dates: str = Field(description="Employment period, e.g. 'Jan 2020 - Present' - must match the source CV exactly")
    bullets: list[str] = Field(
        description=(
            "Exactly 8 achievement-oriented bullet points tailored to the job description. "
            "Each should follow: Action + Technology + Solution + Impact + Numbers."
        )
    )


class SkillCategories(BaseModel):
    """Skills grouped by category, ordered by relevance to the target job description."""

    languages: list[str] = Field(default_factory=list, description="Programming languages")
    backend: list[str] = Field(default_factory=list, description="Backend frameworks/technologies")
    frontend: list[str] = Field(default_factory=list, description="Frontend frameworks/technologies")
    cloud: list[str] = Field(default_factory=list, description="Cloud platforms/services")
    devops: list[str] = Field(default_factory=list, description="DevOps/CI-CD tooling")
    databases: list[str] = Field(default_factory=list, description="Databases/data stores")
    ai: list[str] = Field(default_factory=list, description="AI/ML frameworks and tools")
    tools: list[str] = Field(default_factory=list, description="Other tools (e.g. Git, Jira, Figma)")


class EducationEntry(BaseModel):
    degree: str = Field(description="Degree / qualification name")
    institution: str = Field(description="School / university name")
    dates: str = Field(description="Study period, e.g. '2016 - 2020'")


class ContactInfo(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None


class TailoredResumeContent(BaseModel):
    """The structured, AI-tailored resume content used for both the web
    preview and the generated PDF."""

    contact: ContactInfo
    summary: str = Field(description="2-4 sentence professional summary tailored to the job description")
    skills: SkillCategories = Field(description="Deduplicated skills grouped by category, JD-relevant ones first")
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    languages: list[str] = Field(
        default_factory=list,
        description=(
            "FIXED, backend-only content (see app/core/constants.py's FIXED_LANGUAGES_SECTION) - "
            "always this exact value regardless of the master CV's own Languages section. Never "
            "read from the CV, never AI-generated, never part of ATS keyword matching."
        ),
    )
    certifications: list[str] = Field(
        default_factory=list,
        description=(
            "Certification lines copied VERBATIM from the master CV's Certifications section, "
            "unchanged, in the same order. Empty list if the CV had none. Never invent or remove one."
        ),
    )


class UploadResponse(BaseModel):
    file_id: str
    file_name: str
    cv_text_preview: str = Field(description="First few hundred characters of extracted CV text, for sanity-checking extraction")


class ResumeTemplateInfo(BaseModel):
    """One selectable resume template (see app/db/models.py's ResumeTemplate
    and app/services/template_registry.py). thumbnail_url points at the
    real sample CV page this template was modeled on (served as a static
    file), so the picker shows the actual reference design, not a
    synthetic re-render."""

    slug: str
    name: str
    description: str = ""
    thumbnail_url: str


class CoverLetterDraft(BaseModel):
    """AI-authored cover letter body only. Sender identity, company name,
    and contact header are spliced by the backend from the tailored resume
    and the tailor request - never invented here."""

    greeting: str = Field(description="Salutation, e.g. 'Dear Hiring Manager,'")
    paragraphs: list[str] = Field(description="3-4 body paragraphs of professional prose")
    closing: str = Field(description="Complimentary close, e.g. 'Sincerely,' — without the candidate's name")


class CoverLetterContent(BaseModel):
    """Preview-only cover letter. Never exported as PDF/DOCX."""

    recipient_company: str
    greeting: str
    paragraphs: list[str]
    closing: str
    sender_name: str
    sender_location: str | None = None
    sender_email: str | None = None
    sender_phone: str | None = None


class ApplicationAnswerItem(BaseModel):
    """One employer screening question and the generated answer."""

    question: str
    answer: str


class ApplicationAnswersDraft(BaseModel):
    """AI-authored answers only. Questions are taken from the user list."""

    answers: list[ApplicationAnswerItem] = Field(
        description="One answer per question, same order as the questions in the user message"
    )


class TailorRequest(BaseModel):
    file_id: str
    job_description: str
    main_stack: str = Field(description="Main technology stack for this application, e.g. 'Node.js' - used only for filename generation, never sent to the AI prompt")
    company_name: str = Field(description="Target company name for this application, e.g. 'Sequencer' - used only for filename generation, never sent to the AI prompt")
    template_slug: str = Field(description="Selected resume template slug (see GET /api/resume/templates) - determines the layout the tailored content is rendered into on download")
    include_cover_letter: bool = Field(
        default=False,
        description="If true, generate a preview-only cover letter from the JD and tailored resume after tailoring",
    )
    application_questions: list[str] = Field(
        default_factory=list,
        description="Optional employer screening questions, added one by one. Empty means skip answer generation.",
        max_length=12,
    )


class AtsMatchInfo(BaseModel):
    """Estimated ATS keyword-match score against the job description.

    This is a lexical-overlap approximation (how lightweight ATS keyword
    scanners work), not a guarantee of any specific external tool's score.
    """

    score: float = Field(ge=0, le=1, description="Fraction (0-1) of job description keywords found in the resume")
    matched_keywords: list[str]
    missing_keywords: list[str]


class TailorResponse(BaseModel):
    file_id: str
    resume: TailoredResumeContent
    ats_match: AtsMatchInfo
    generated_filename: str = Field(
        description="Zip base name (no extension), e.g. 'Mateo Baranji_node_asd'. "
        "The CV file inside the zip is the candidate's name only."
    )
    template_slug: str
    cover_letter: CoverLetterContent | None = Field(
        default=None,
        description="Preview-only cover letter when include_cover_letter was true; otherwise null",
    )
    application_answers: list[ApplicationAnswerItem] = Field(
        default_factory=list,
        description="Preview-only answers to application_questions, grounded in the tailored resume",
    )


# --- Filename generation + "resume history" storage ------------------------
#
# ResumeMetadata mirrors app/db/models.py's ResumeRecord row for a given
# file_id (see app/services/template_registry.py / app/db/session.py) -
# /download looks up the generated filename + template by file_id, and
# /history lists every past ResumeRecord, most recent first.


class ResumeMetadata(BaseModel):
    id: int
    candidate_name: str
    main_stack: str
    company_name: str
    generated_filename: str
    template_slug: str
    created_at: str = Field(description="ISO 8601 UTC timestamp")


# --- Structured master-CV cache (see app/services/cv_structurer.py) --------
#
# Parsed once at upload time (no AI) so /tailor never has to re-parse or
# re-send the raw CV text. When is_structured is False (PDF upload, or a
# DOCX whose layout couldn't be confidently segmented), the structured
# fields are left empty and ai_tailor.py falls back to the original
# raw-text prompt using raw_text instead.


class CvExperienceEntry(BaseModel):
    title: str = ""
    company: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class MasterCvData(BaseModel):
    contact: ContactInfo
    summary: str = ""
    skills_raw: list[str] = Field(default_factory=list)
    experience: list[CvExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    languages_raw: list[str] = Field(
        default_factory=list,
        description="Raw lines from the CV's own Languages section, verbatim, if any. Extracted for completeness only - the tailored resume's Languages section is now a FIXED backend value (see app/core/constants.py), never sourced from this field.",
    )
    certifications_raw: list[str] = Field(
        default_factory=list,
        description="Raw lines from the CV's Certifications section, verbatim - never sent to or altered by the AI, spliced straight into the output.",
    )
    is_structured: bool = False
    raw_text: str = ""


# --- No-AI job description analysis (see app/services/jd_analyzer.py) ------


class JdAnalysis(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list, description="Flat union of all categorized tech lists below - kept for resume_matcher term collection")
    responsibilities: list[str] = Field(default_factory=list)
    seniority: str = ""

    # Finer-grained categorization (all heuristic/regex-based, no AI) so the
    # tailoring prompt can address more than raw keyword overlap - matching
    # architecture, domain, and practices, not just tech-name insertion.
    target_job_title: str = Field(default="", description="The role's title, extracted from an explicit 'Job Title:'/'Position:' line or the JD's opening line")
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    cloud_platforms: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    devops_tools: list[str] = Field(default_factory=list)
    ai_ml_tools: list[str] = Field(default_factory=list)
    methodologies: list[str] = Field(default_factory=list, description="e.g. Agile, Scrum, TDD, CI/CD")
    soft_skills: list[str] = Field(default_factory=list, description="e.g. leadership, mentoring, stakeholder management")
    business_domain: str = Field(default="", description="e.g. Fintech, Healthcare, E-commerce - detected from JD keywords")
    qualifications: list[str] = Field(default_factory=list, description="Formal qualification lines (degree/certification/years) distinct from pure tech-skill lines")
    certifications: list[str] = Field(default_factory=list, description="Named certifications mentioned in the JD (e.g. 'AWS Certified Solutions Architect')")
    required_years_experience: str = Field(default="", description="e.g. '5+ years'")


# --- No-AI resume <-> JD matching (see app/services/resume_matcher.py) -----


class ResumeMatch(BaseModel):
    matched_skills: list[str] = Field(default_factory=list)
    transferable_skills: list[str] = Field(
        default_factory=list, description="JD skills not directly listed but found in bullet text - hints for the AI, not fabrication"
    )
    missing_skills: list[str] = Field(default_factory=list)
    # Preferred / nice-to-have JD skills the CV can support (subset of
    # matched/transferable). The tailor must weave these into summary +
    # skills + bullets the same way as required — ChatGPT-style coverage.
    preferred_matched: list[str] = Field(
        default_factory=list,
        description="Nice-to-have / preferred JD terms already demonstrated on the CV",
    )
    preferred_transferable: list[str] = Field(
        default_factory=list,
        description="Nice-to-have JD terms transferable from related CV skills (same format as transferable_skills)",
    )
    prioritized_job_indices: list[int] = Field(default_factory=list, description="master_cv.experience indices, most JD-relevant first")
    preliminary_score: float = Field(default=0.0, ge=0, le=1)


# --- AI output schema for the structured/dynamic-content path -------------
#
# Used only when MasterCvData.is_structured is True. Company names,
# employment dates, contact info, and education are never sent to or
# generated by the AI in this path - they're spliced in verbatim from
# MasterCvData by app/services/ai_tailor.py, guaranteeing they can never be
# altered and shrinking prompt tokens. Summary, Skills, and per-job bullets
# ARE generated by the AI - JD-driven rather than restricted to what the
# candidate's real CV already shows (see app/prompts/resume_tailor_prompt.py).
# Job titles may also be suggested here, but the backend always uses the
# master CV's own original title in the final output.


class DynamicExperienceContent(BaseModel):
    title: str = Field(description="Suggested job title (terminology only) - the backend always uses the master CV's own original title instead")
    bullets: list[str] = Field(
        description=(
            "Exactly EXPERIENCE_BULLET_COUNT achievement-oriented bullets, generated to best fit the "
            "job description - not limited to this job's real original duties."
        )
    )


class TailoredDynamicContent(BaseModel):
    summary: str
    skills: SkillCategories = Field(
        description="Full JD-relevant skill set - not limited to skills already on the candidate's CV"
    )
    experience: list[DynamicExperienceContent]


class ValidationReport(BaseModel):
    """Result of app/services/resume_validator.py's deterministic, no-AI
    post-generation checks. Company/date mismatches and duplicate bullets
    are auto-corrected in place; issues lists what was found/fixed."""

    issues: list[str] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.issues


class UserPublic(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_approved: bool = False
    is_active: bool = True


class AdminUserActivity(BaseModel):
    id: int
    candidate_name: str
    main_stack: str
    company_name: str
    generated_filename: str
    created_at: str


class AdminUserRow(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_approved: bool
    is_active: bool
    created_at: str
    resume_count: int
    activity: list[AdminUserActivity] = Field(default_factory=list)


class AdminUserUpdate(BaseModel):
    is_approved: bool | None = None
    is_active: bool | None = None


class AuthConfigResponse(BaseModel):
    google_client_id: str = ""


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    credential: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic
