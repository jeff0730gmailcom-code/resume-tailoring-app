"""ATS keyword-match scoring.

Estimates how well a tailored resume covers the significant keywords in a
job description, using simple lexical overlap (how most lightweight ATS
keyword scanners actually work: literal/near-literal term matching, not
semantic similarity). This is an approximation — different ATS tools score
differently — but it gives a concrete, actionable signal we can use to
drive the AI refinement loop in app/services/ai_tailor.py.

The keyword denominator (see _jd_keyword_set) is scored against the JD's
structured requirement fields (jd_analyzer.py's required/preferred skills,
technologies, responsibilities, methodologies, soft skills) whenever
available, NOT the whole raw JD text - a real job posting is mostly company/
benefits/EEO boilerplate that no amount of truthful tailoring could ever
"match", so including it in the denominator was making a 95%+ score
structurally unreachable regardless of tailoring quality.
"""
import re
from functools import lru_cache

from app.models.schemas import AtsMatchInfo, JdAnalysis, TailoredResumeContent

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "to",
    "of", "in", "on", "at", "by", "with", "from", "as", "is", "are", "was",
    "were", "be", "been", "being", "this", "that", "these", "those", "it",
    "its", "we", "you", "your", "they", "their", "our", "us", "he", "she",
    "his", "her", "them", "i", "me", "my", "who", "whom", "which", "what",
    "will", "would", "can", "could", "should", "shall", "may", "might",
    "must", "have", "has", "had", "do", "does", "did", "not", "no", "so",
    "than", "too", "very", "just", "about", "into", "over", "under", "up",
    "down", "out", "off", "again", "further", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "only", "own", "same",
    "per", "etc", "please", "job", "role", "responsibilities", "responsible",
    "requirements", "required", "preferred", "qualifications", "candidate",
    "candidates", "company", "years", "year", "including", "including",
    "using", "based", "within", "across", "ability", "abilities", "strong",
    "excellent", "experience", "experienced", "work", "working", "team",
    "teams", "including", "etc", "e.g", "eg", "looking", "plus", "you'll",
    "we're", "join", "help", "make", "new", "also", "well", "good",
    # JD boilerplate that isn't an actual skill/qualification keyword
    "bachelor", "bachelors", "master", "masters", "degree", "diploma",
    "equivalent", "employer", "employment", "employees", "employee",
    "compensation", "salary", "benefits", "insurance", "equal",
    "opportunity", "disability", "veteran", "race", "gender", "religion",
    "apply", "application", "applicants", "resume", "cover", "letter",
    "office", "onsite", "remote", "hybrid", "travel", "location",
    "position", "positions", "full-time", "part-time", "contract",
    "hire", "hiring", "growing", "fast-paced", "environment", "culture",
    "mission", "vision", "values", "diverse", "inclusion", "inclusive",
    "world", "global", "industry", "background", "passion", "passionate",
    "self-starter", "motivated", "detail-oriented", "fast", "paced",
    "note", "eeo", "aa", "aap", "knowledge", "need", "needed", "needs",
    "familiarity", "familiar", "understanding", "solid", "deep", "proven",
    "demonstrated", "hands-on", "hand", "you", "we", "our", "the", "will",
    # Section-heading/label artifacts (e.g. "Job Title:", "Required
    # Skills:") - these are JD document structure, never a real
    # skill/requirement, and would otherwise unfairly inflate the keyword
    # denominator on any JD formatted with explicit section labels.
    "title", "titled", "skill", "skills", "field", "fields", "related",
    "conduct", "conducted", "drive", "driven", "driving", "professional",
    "professionally", "dynamic", "cutting-edge", "state-of-the-art",
    "tool", "tools", "methodology", "methodologies", "fast-growing",
    "fast-paced", "fastgrowing", "similar", "similarly",
}

_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.#/_-]{1,}")


@lru_cache(maxsize=256)
def _extract_keywords(text: str) -> frozenset[str]:
    """Cached: within a single tailor_resume() call, the job description is
    re-scored on every ATS refinement iteration but its keyword set never
    changes, so this avoids redundant regex/tokenization work each time.
    Returns a frozenset since the result is shared across cache hits."""
    raw_tokens = _TOKEN_PATTERN.findall(text.lower())
    keywords: set[str] = set()
    for raw in raw_tokens:
        token = raw.strip(".,-")
        if len(token) > 2 and token not in _STOPWORDS:
            keywords.add(token)
        # Slash-joined compounds (e.g. "agile/scrum", "ci/cd") rarely
        # appear verbatim with identical punctuation on the other side
        # (a resume is far more likely to say "Agile and Scrum" or "Agile /
        # Scrum" than the exact compound) - also register their individual
        # parts so either form of phrasing counts as covering the JD term.
        if "/" in token:
            for part in token.split("/"):
                part = part.strip(".,-")
                if len(part) > 2 and part not in _STOPWORDS:
                    keywords.add(part)
    return frozenset(keywords)


def _build_word_families() -> dict[str, str]:
    """Curated noun<->verb word-family groups mapped to a shared root, for
    pairs the generic suffix-stripper below can't handle (it only trims
    endings, so it can't relate e.g. "collaboration" to "collaborated", or
    "methodologies" to "methodology" - both very common JD-vs-resume
    phrasing mismatches: JDs favor abstract nouns ("collaboration",
    "optimization", "leadership"), resumes favor concrete past-tense verbs
    ("collaborated", "optimized", "led"). Missing this was silently
    deflating ATS scores across almost every JD/resume pair, not just
    edge cases."""
    families: dict[str, str] = {}

    def register(root: str, *words: str) -> None:
        for word in words:
            families[word] = root

    register("collaborat", "collaboration", "collaborate", "collaborated", "collaborating", "collaborative", "collaborator", "collaborators")
    register("optimiz", "optimization", "optimizations", "optimize", "optimized", "optimizing", "optimal", "optimally")
    register("automat", "automation", "automate", "automated", "automating", "automatic", "automatically")
    register("mentor", "mentorship", "mentor", "mentored", "mentoring", "mentors")
    register("document", "documentation", "document", "documented", "documenting", "documents")
    register("communicat", "communication", "communicate", "communicated", "communicating", "communications")
    register("implement", "implementation", "implement", "implemented", "implementing", "implementations")
    register("integrat", "integration", "integrate", "integrated", "integrating", "integrations")
    register("migrat", "migration", "migrate", "migrated", "migrating", "migrations")
    register("configur", "configuration", "configure", "configured", "configuring", "configurations")
    register("administ", "administration", "administer", "administered", "administering", "administrator", "administrators")
    register("architect", "architecture", "architect", "architected", "architecting", "architectures", "architects")
    register("certif", "certification", "certify", "certified", "certifying", "certifications", "certificate", "certificates")
    register("lead", "leadership", "lead", "led", "leading", "leader", "leaders")
    register("manag", "management", "manage", "managed", "managing", "manager", "managers")
    register("develop", "development", "develop", "developed", "developing", "developer", "developers")
    register("deploy", "deployment", "deploy", "deployed", "deploying", "deployments")
    register("monitor", "monitoring", "monitor", "monitored", "monitors")
    register("scal", "scaling", "scale", "scaled", "scalable", "scales", "scalability")
    register("analy", "analysis", "analyze", "analyzed", "analyzing", "analytics", "analytical", "analyst", "analysts")
    register("evaluat", "evaluation", "evaluate", "evaluated", "evaluating", "evaluations")
    register("coordinat", "coordination", "coordinate", "coordinated", "coordinating")
    register("execut", "execution", "execute", "executed", "executing")
    register("deliver", "delivery", "deliver", "delivered", "delivering", "deliverables")
    register("own", "ownership", "own", "owned", "owning", "owner", "owners")
    register("secur", "security", "secure", "secured", "securing")
    register("perform", "performance", "perform", "performed", "performing")
    register("innovat", "innovation", "innovate", "innovated", "innovating", "innovative")
    register("methodolog", "methodology", "methodologies")
    register("technolog", "technology", "technologies")
    register("respons", "responsibility", "responsibilities", "responsible")
    # Common resume/JD verbs ending in a silent "e" - the generic
    # suffix-stripper below can't relate these to their "-ed"/"-ing" forms
    # because English drops the "e" before adding the suffix (e.g.
    # "improve" + "ed" = "improved", not "improveed"), so "improve" and
    # "improved" would otherwise stem to different strings and never match.
    register("improv", "improve", "improves", "improved", "improving", "improvement", "improvements")
    register("creat", "create", "creates", "created", "creating", "creation", "creations")
    register("generat", "generate", "generates", "generated", "generating", "generation")
    register("reduc", "reduce", "reduces", "reduced", "reducing", "reduction", "reductions")
    register("increas", "increase", "increases", "increased", "increasing")
    register("produc", "produce", "produces", "produced", "producing", "production")
    register("provid", "provide", "provides", "provided", "providing", "provider", "providers")
    register("driv", "drive", "drives", "drove", "driven", "driving")
    # Irregular verb, unrelated to any regular suffix pattern.
    register("writ", "write", "writes", "writing", "wrote", "written")
    return families


_WORD_FAMILIES = _build_word_families()


def _stem(token: str) -> str:
    """Light stemming so word-form differences don't register as
    mismatches. Checks the curated noun<->verb word-family map first (see
    _build_word_families), falling back to generic suffix-stripping
    (handles regular plurals/tenses like "mentor" vs "mentored", "pipeline"
    vs "pipelines", "company" vs "companies") for everything else not in
    that curated list. Guarded by a minimum length so short technical terms
    (e.g. "aws", "css") are never stemmed."""
    family_root = _WORD_FAMILIES.get(token)
    if family_root:
        return family_root
    if len(token) <= 5:
        return token
    if token.endswith("ies") and len(token) - 3 > 3:
        return token[:-3] + "y"
    for suffix in ("ing", "edly", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) > 3:
            return token[: -len(suffix)]
    return token


def _flatten_resume_text(resume: TailoredResumeContent) -> str:
    parts: list[str] = [resume.summary]

    skills = resume.skills
    for field in ("languages", "backend", "frontend", "cloud", "devops", "databases", "ai", "tools"):
        parts.extend(getattr(skills, field))

    for entry in resume.experience:
        parts.append(entry.title)
        parts.append(entry.company)
        parts.extend(entry.bullets)

    for entry in resume.education:
        parts.append(entry.degree)
        parts.append(entry.institution)

    # Certifications are preserved verbatim from the master CV (see
    # MasterCvData.certifications_raw) but are 100% real candidate content
    # and must count toward ATS coverage just like any other section - e.g.
    # a certifications line literally containing "AWS Certified Solutions
    # Architect" should credit the JD keywords "aws"/"certified"/
    # "architect"/"solutions" without the AI needing to redundantly restate
    # it elsewhere.
    #
    # resume.languages (the spoken-language proficiency section, e.g.
    # "English — C1") is deliberately NOT included here - it's a fixed,
    # backend-only section (see app/core/constants.py) that must never
    # factor into ATS keyword matching. Note this is unrelated to
    # resume.skills.languages (programming languages, e.g. Python/Java),
    # which IS included above via the skills-category loop.
    parts.extend(resume.certifications)

    return " ".join(parts)


def _jd_keyword_set(job_description: str, jd_analysis: JdAnalysis | None) -> frozenset[str]:
    """The scoring denominator - which JD keywords a resume is judged against.

    When jd_analysis (see app/services/jd_analyzer.py, no AI) is available
    and its heuristic section-parsing found real content, score against
    ONLY the JD's genuine requirement fields (required/preferred skills,
    technologies, responsibilities, methodologies, soft skills, target job
    title) - NOT the whole raw JD text. This matters a lot in practice: a
    real JD posting is majority company blurb, benefits, EEO boilerplate,
    and application instructions, none of which a resume should or could
    ever "match" - scoring against the full text was silently making 95%+
    unreachable by inflating the denominator with terms no tailoring could
    ever legitimately cover. Falls back to whole-text extraction only when
    jd_analysis isn't available or found no structured sections (unusual JD
    formatting) - never scores against LESS information than before.
    """
    if jd_analysis is not None:
        structured_fields: list[str] = [
            *jd_analysis.required_skills,
            *jd_analysis.preferred_skills,
            *jd_analysis.technologies,
            *jd_analysis.responsibilities,
            *jd_analysis.methodologies,
            *jd_analysis.soft_skills,
        ]
        if jd_analysis.target_job_title:
            structured_fields.append(jd_analysis.target_job_title)
        if structured_fields:
            return _extract_keywords(" ".join(structured_fields))
    return _extract_keywords(job_description)


def compute_ats_match(
    resume: TailoredResumeContent,
    job_description: str,
    jd_analysis: JdAnalysis | None = None,
) -> AtsMatchInfo:
    """Estimate ATS keyword-match score (0-1) between the tailored resume and
    the job description, plus which JD keywords are matched/missing.

    jd_analysis, when passed (every real call site already has one computed
    upstream - see app/services/jd_analyzer.py), scores against the JD's
    structured requirement fields rather than its entire raw text - see
    _jd_keyword_set's docstring for why that's the more meaningful and more
    fairly-reachable denominator. Optional (defaults to the old whole-text
    behavior) only so this function still works standalone/in tests without
    requiring a JdAnalysis to be constructed first.
    """
    jd_keywords = _jd_keyword_set(job_description, jd_analysis)
    resume_keywords = _extract_keywords(_flatten_resume_text(resume))

    if not jd_keywords:
        return AtsMatchInfo(score=1.0, matched_keywords=[], missing_keywords=[])

    resume_stems = {_stem(k) for k in resume_keywords}
    matched = sorted(k for k in jd_keywords if _stem(k) in resume_stems)
    missing = sorted(k for k in jd_keywords if _stem(k) not in resume_stems)
    score = len(matched) / len(jd_keywords)

    return AtsMatchInfo(score=round(score, 4), matched_keywords=matched, missing_keywords=missing)
