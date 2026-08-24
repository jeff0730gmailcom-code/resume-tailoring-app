"""No-AI resume <-> job-description matching — "Step 3" of the pipeline.

Compares the structured master CV (app/services/cv_structurer.py) against
the no-AI job-description analysis (app/services/jd_analyzer.py) to work
out, before any OpenAI call: which JD skills the candidate already
demonstrates, which are plausibly transferable from a related skill already
on the CV, which are missing outright, and which jobs are most JD-relevant.

This is fed into the AI prompt as pre-computed guidance (see
app/prompts/resume_tailor_prompt.py's build_structured_user_message) so the
model spends its output budget writing good prose instead of re-deriving
this matching itself — shrinking prompt size and the model's own reasoning
work. "Transferable" is only ever a hint to *tie real CV-supported work to
the JD term* (per .cursor/rules/resume-tailoring-prompt-rules.mdc) — never
an instruction to fabricate hands-on experience.
"""
from app.models.schemas import JdAnalysis, MasterCvData, ResumeMatch
from app.services.ats_scorer import _extract_keywords, _stem
from app.services.jd_analyzer import _METHODOLOGIES, _TECHNOLOGY_TERMS

# Generic tokens extracted from preferred lines that are not real skills.
_PREFERRED_NOISE = {
    "api", "apis", "caching", "experience", "experiences", "applications",
    "services", "systems", "tools", "software", "development", "knowledge",
    "ability", "strong", "years", "plus", "bonus", "preferred", "nice",
    "have", "good", "working", "using", "etc", "including", "related",
}

# Small "same category" groupings used only to flag transferable-skill
# hints (e.g. CV has MySQL, JD wants PostgreSQL -> both relational DBs).
# Deliberately small and conservative — false negatives just mean a skill
# is reported as "missing" instead of "transferable", which is the safe
# direction to be wrong in. Used in ALL THREE tailoring modes.
_SKILL_FAMILIES: list[set[str]] = [
    {"aws", "azure", "gcp", "cloud"},
    {"mysql", "postgresql", "postgres", "mssql", "oracle", "sqlite", "mariadb", "sql"},
    {"mongodb", "dynamodb", "cassandra", "couchbase", "firestore", "nosql"},
    {"kafka", "rabbitmq", "sqs", "activemq", "pubsub"},
    {"docker", "kubernetes", "containerd", "podman"},
    {"react", "vue", "angular", "svelte"},
    {"django", "flask", "fastapi", "express", "spring", "rails"},
    {"jenkins", "gitlab", "circleci", "github", "travis"},
    {"terraform", "ansible", "puppet", "chef", "cloudformation"},
]

# Broader/looser groupings consulted in "aggressive" AND "aggressive_match"
# mode, as a second pass after _SKILL_FAMILIES finds nothing. Wider net
# (more categories, more members per category) means these modes surface
# more genuine transferable connections than accurate mode - e.g. flags a
# data-warehouse JD term against a candidate who's only listed a different
# data-warehouse tool. Still just a *hint to tie real work to the JD term*,
# same as _SKILL_FAMILIES - never a license to claim hands-on experience
# with something that has no connection at all to the candidate's background.
_AGGRESSIVE_SKILL_FAMILIES: list[set[str]] = [
    {"aws", "azure", "gcp", "cloud", "lambda", "ec2", "s3", "heroku", "vercel", "netlify", "digitalocean"},
    {
        "mysql", "postgresql", "postgres", "mssql", "oracle", "sqlite", "mariadb", "sql",
        "snowflake", "bigquery", "redshift", "databricks",
    },
    {"mongodb", "dynamodb", "cassandra", "couchbase", "firestore", "nosql", "redis"},
    {"kafka", "rabbitmq", "sqs", "sns", "activemq", "pubsub", "eventbridge"},
    {"docker", "kubernetes", "containerd", "podman", "helm", "ecs", "eks", "openshift"},
    {"react", "vue", "angular", "svelte", "nextjs", "nuxt", "ember"},
    {"django", "flask", "fastapi", "express", "spring", "rails", "laravel", "nestjs"},
    {"jenkins", "gitlab", "circleci", "github", "travis", "teamcity", "bamboo", "argo", "actions"},
    {"terraform", "ansible", "puppet", "chef", "cloudformation", "pulumi"},
    {"agile", "scrum", "kanban", "waterfall", "safe"},
    {"junit", "pytest", "selenium", "cypress", "jest", "mocha", "testng"},
    {"tableau", "powerbi", "looker", "grafana", "kibana", "datadog", "splunk"},
    {"graphql", "grpc", "rest", "soap", "websocket"},
]

# Broadest tier, consulted ONLY in "aggressive_match" mode (AGGRESSIVE_MATCH_MODE),
# as a third pass after both tiers above find nothing. Groups by *problem
# category* rather than by close technical similarity (e.g. every cloud
# compute flavor - VMs, containers, serverless - is one family; every
# messaging/event-streaming system is one family) - this is still a hint to
# tie a JD skill to genuinely-related real work, never a license to claim
# hands-on experience with something that has zero connection to anything in
# the CV. A JD skill absent from all three tiers is still reported as
# "missing" and left out, in this mode too.
_MATCH_MODE_SKILL_FAMILIES: list[set[str]] = [
    {
        "aws", "azure", "gcp", "cloud", "lambda", "ec2", "ecs", "eks", "fargate", "s3",
        "heroku", "vercel", "netlify", "digitalocean", "serverless", "cloud functions",
        "azure functions", "kubernetes", "docker", "containerd", "podman", "openshift",
    },
    {
        "mysql", "postgresql", "postgres", "mssql", "oracle", "sqlite", "mariadb", "sql",
        "nosql", "snowflake", "bigquery", "redshift", "databricks", "mongodb", "dynamodb",
        "cassandra", "couchbase", "firestore", "redis",
    },
    {
        "kafka", "rabbitmq", "sqs", "sns", "activemq", "pubsub", "eventbridge", "kinesis",
        "nats", "event-driven", "message queue", "messaging",
    },
    {
        "terraform", "ansible", "puppet", "chef", "cloudformation", "pulumi", "ci/cd",
        "jenkins", "gitlab", "circleci", "github actions", "automation",
        "infrastructure as code", "devops",
    },
    {"react", "vue", "angular", "svelte", "nextjs", "nuxt", "ember", "frontend"},
    {
        "django", "flask", "fastapi", "express", "spring", "rails", "laravel", "nestjs",
        "node.js", "nodejs", "backend",
    },
    {"agile", "scrum", "kanban", "waterfall", "safe", "methodology"},
    {"junit", "pytest", "selenium", "cypress", "jest", "mocha", "testng", "testing"},
    {
        "tableau", "powerbi", "looker", "grafana", "kibana", "datadog", "splunk",
        "monitoring", "observability",
    },
    {"graphql", "grpc", "rest", "soap", "websocket", "api"},
    {"tensorflow", "pytorch", "scikit-learn", "keras", "machine learning", "ai", "llm", "nlp"},
]


def match_resume_to_jd(
    master_cv: MasterCvData, jd_analysis: JdAnalysis, mode: str = "accurate"
) -> ResumeMatch:
    """Pure in-memory comparison - no AI, no I/O. Runs in well under a
    millisecond for typical CV/JD sizes.

    mode="aggressive" additionally consults _AGGRESSIVE_SKILL_FAMILIES (a
    wider net); mode="aggressive_match" (AGGRESSIVE_MATCH_MODE) additionally
    consults _MATCH_MODE_SKILL_FAMILIES too (the widest net) before giving
    up on a JD term as "missing" - each tier finds more genuine transferable
    connections, none of them invent ones that aren't there. A term with no
    match in any tier available to the current mode is still reported as
    missing.

    Preferred / nice-to-have terms the CV can support are also returned in
    preferred_matched / preferred_transferable so the prompt and gap-closer
    can force them into the tailored CV (ChatGPT-style coverage).
    """
    resume_keywords = _extract_keywords(_flatten_master_cv(master_cv))
    resume_stems = {_stem(k) for k in resume_keywords}
    # Also treat explicit skills_raw tokens as stems (some CVs list skills
    # that keyword extraction on prose under-counts).
    for skill in master_cv.skills_raw:
        resume_stems |= {_stem(k) for k in _extract_keywords(skill)}
        resume_stems.add(_stem(skill))

    jd_terms = _collect_jd_terms(jd_analysis)
    preferred_terms = _collect_preferred_terms(jd_analysis)
    preferred_stems = {_stem(t) for t in preferred_terms}

    matched = sorted(term for term in jd_terms if _stem(term) in resume_stems)
    unmatched = [term for term in jd_terms if _stem(term) not in resume_stems]

    transferable: list[str] = []
    truly_missing: list[str] = []
    for term in unmatched:
        related = _find_related_existing_skill(term, resume_stems)
        if not related and mode in ("aggressive", "aggressive_match"):
            related = _find_related_existing_skill(term, resume_stems, families=_AGGRESSIVE_SKILL_FAMILIES)
        if not related and mode == "aggressive_match":
            related = _find_related_existing_skill(term, resume_stems, families=_MATCH_MODE_SKILL_FAMILIES)
        if related:
            transferable.append(f"{term} (related: {related})")
        else:
            truly_missing.append(term)

    score = len(matched) / len(jd_terms) if jd_terms else 1.0

    preferred_matched = sorted(t for t in matched if _stem(t) in preferred_stems)
    preferred_transferable = sorted(
        e for e in transferable if _stem(e.split(" (related:")[0].strip()) in preferred_stems
    )

    return ResumeMatch(
        matched_skills=matched,
        transferable_skills=sorted(transferable),
        missing_skills=sorted(truly_missing),
        preferred_matched=preferred_matched,
        preferred_transferable=preferred_transferable,
        prioritized_job_indices=_prioritize_jobs(master_cv, jd_terms),
        preliminary_score=round(score, 4),
    )


def _collect_jd_terms(jd_analysis: JdAnalysis) -> set[str]:
    terms: set[str] = set(jd_analysis.technologies)
    # Fold in every categorized list too (programming_languages, frameworks,
    # cloud_platforms, etc.) - these come from substring search over the
    # full JD text (see jd_analyzer._match_category), so they catch
    # multi-word terms (e.g. "google cloud") that technologies' pure
    # keyword-token matching can miss.
    for category in (
        jd_analysis.programming_languages,
        jd_analysis.frameworks,
        jd_analysis.cloud_platforms,
        jd_analysis.databases,
        jd_analysis.devops_tools,
        jd_analysis.ai_ml_tools,
        jd_analysis.methodologies,
    ):
        terms |= set(category)
    for line in jd_analysis.required_skills + jd_analysis.preferred_skills:
        terms |= _extract_keywords(line)
    return terms


def _collect_preferred_terms(jd_analysis: JdAnalysis) -> set[str]:
    """Terms that came from preferred / nice-to-have JD lines (and tech
    tokens that only appear in those lines). Used to prioritize ChatGPT-
    style inclusion of CV-supported nice-to-haves."""
    terms: set[str] = set()
    preferred_text = " ".join(jd_analysis.preferred_skills).lower()
    if not preferred_text:
        return terms
    for line in jd_analysis.preferred_skills:
        for token in _extract_keywords(line):
            if _is_meaningful_preferred_term(token):
                terms.add(token)
    # Named tech / practices present in preferred lines specifically.
    for category in (
        jd_analysis.programming_languages,
        jd_analysis.frameworks,
        jd_analysis.cloud_platforms,
        jd_analysis.databases,
        jd_analysis.devops_tools,
        jd_analysis.ai_ml_tools,
        jd_analysis.methodologies,
    ):
        for term in category:
            if term in preferred_text:
                terms.add(term)
    return terms


def _is_meaningful_preferred_term(term: str) -> bool:
    lower = term.lower().strip()
    if not lower or lower in _PREFERRED_NOISE or len(lower) < 2:
        return False
    if lower in _TECHNOLOGY_TERMS or lower in _METHODOLOGIES:
        return True
    # Keep other concrete tokens from preferred bullets (product names, etc.).
    return len(lower) >= 4 and lower.replace(".", "").replace("/", "").isalnum()


def _find_related_existing_skill(
    term: str, resume_stems: set[str], families: list[set[str]] = _SKILL_FAMILIES
) -> str | None:
    for family in families:
        if term not in family:
            continue
        for candidate in family:
            if candidate != term and _stem(candidate) in resume_stems:
                return candidate
    return None


def _flatten_master_cv(master_cv: MasterCvData) -> str:
    if not master_cv.is_structured:
        return master_cv.raw_text
    parts = [master_cv.summary, *master_cv.skills_raw]
    for entry in master_cv.experience:
        parts.append(entry.title)
        parts.extend(entry.bullets)
    return " ".join(parts)


def _prioritize_jobs(master_cv: MasterCvData, jd_terms: set[str]) -> list[int]:
    """Rank master_cv.experience indices by JD-keyword overlap, most
    relevant first (stable: ties keep original CV order)."""
    if not master_cv.experience:
        return []

    scored: list[tuple[int, int]] = []
    for idx, entry in enumerate(master_cv.experience):
        entry_keywords = _extract_keywords(" ".join([entry.title, *entry.bullets]))
        entry_stems = {_stem(k) for k in entry_keywords}
        overlap = sum(1 for term in jd_terms if _stem(term) in entry_stems)
        scored.append((-overlap, idx))
    scored.sort()
    return [idx for _, idx in scored]
