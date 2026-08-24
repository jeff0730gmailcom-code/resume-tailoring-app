"""No-AI job description analysis — "Step 2" of the pipeline.

Purely heuristic (regex + line-based section splitting): extracts keywords,
required vs. preferred skills, named technologies, responsibility bullets,
a seniority signal, and finer categorization (target job title, per-category
tech stacks, methodologies, soft skills, business domain, certifications,
required years of experience) from the pasted job description text. Feeds
app/services/resume_matcher.py and the compact AI prompt builder in
app/prompts/resume_tailor_prompt.py — no OpenAI call involved.

The finer categorization exists so tailoring can go beyond keyword overlap -
matching architecture/domain/practices, not just inserting tech names (see
RESUME TAILORING RULES in app/prompts/resume_tailor_prompt.py).
"""
import re

from app.models.schemas import JdAnalysis
from app.services.ats_scorer import _extract_keywords

# Cap on every categorized list sent into the prompt - keeps prompt size in
# check even as JDs get longer/more categories get added; the highest-signal
# items (first mentioned/most specific) matter far more than an exhaustive list.
_MAX_ITEMS_PER_CATEGORY = 12

_REQUIRED_HEADING_RE = re.compile(
    r"^(requirements?|required\s+skills?|must[\s-]have|qualifications?|"
    r"minimum\s+qualifications?|what\s+you.?ll\s+need|you\s+have|"
    r"basic\s+qualifications?)\s*:?\s*$",
    re.IGNORECASE,
)
_PREFERRED_HEADING_RE = re.compile(
    r"^(preferred|preferred\s+skills?|preferred\s+qualifications?|"
    r"nice[\s-]to[\s-]have|bonus\s+points?|pluses?|good\s+to\s+have|"
    r"desirable|additional\s+skills?|optional\s+skills?)\s*:?\s*$",
    re.IGNORECASE,
)
# Inline cues that mark a bullet as preferred even under a required heading
# or in unstructured JD text (ChatGPT-style "nice to have" coverage).
_INLINE_PREFERRED_RE = re.compile(
    r"(nice[\s-]to[\s-]have|is a plus|would be a plus|preferred|"
    r"bonus|good to have|desirable|ideally|optional)",
    re.IGNORECASE,
)
_RESPONSIBILITY_HEADING_RE = re.compile(
    r"^(responsibilities|what\s+you.?ll\s+do|the\s+role|duties|"
    r"day[\s-]to[\s-]day|key\s+responsibilities)\s*:?\s*$",
    re.IGNORECASE,
)
_OTHER_HEADING_RE = re.compile(
    r"^(about(\s+us)?|role\s+overview|company|benefits|compensation|why\s+"
    r"join|the\s+team|overview|location|equal\s+opportunity|perks)\s*:?\s*$",
    re.IGNORECASE,
)
_BULLET_PREFIX_RE = re.compile(r"^\s*[•‣▪●◦○\-\*\u2013\u2014]\s+")

_SENIORITY_PATTERNS = [
    (re.compile(r"\b(principal|staff)\b", re.IGNORECASE), "Principal/Staff"),
    (re.compile(r"\bsenior\b|\bsr\.?\b", re.IGNORECASE), "Senior"),
    (re.compile(r"\blead\b", re.IGNORECASE), "Lead"),
    (re.compile(r"\bmid[\s-]?level\b|\bintermediate\b", re.IGNORECASE), "Mid-level"),
    (re.compile(r"\bjunior\b|\bjr\.?\b|\bentry[\s-]?level\b|\bnew\s+grad\b", re.IGNORECASE), "Junior/Entry-level"),
]
_YEARS_RE = re.compile(r"(\d+)\+?\s*(?:-\s*\d+\s*)?\s*years?", re.IGNORECASE)

# Per-category curated dictionaries. Deliberately overlapping with each
# other's neighbors is fine (e.g. "sql" appears nowhere but "postgresql"
# does under databases) - each dict only needs to be useful for its own
# category, not mutually exclusive; a term can also appear in the flat
# `technologies` union regardless of which specific category caught it.
_PROGRAMMING_LANGUAGES = {
    "python", "javascript", "typescript", "java", "kotlin", "swift", "go",
    "golang", "rust", "php", "ruby", "scala", "c++", "c#", "c", "perl", "r",
    "dart", "objective-c", "elixir", "haskell", "clojure", "matlab",
}
_FRAMEWORKS = {
    "react", "angular", "vue", "nextjs", "nuxt", "django", "flask",
    "fastapi", "spring", "express", "rails", "laravel", "nestjs", "svelte",
    "dotnet", ".net", "asp.net", "ember", "backbone", "gatsby", "remix",
}
_CLOUD_PLATFORMS = {
    "aws", "azure", "gcp", "google cloud", "heroku", "digitalocean",
    "cloudflare", "vercel", "netlify", "oracle cloud", "ibm cloud",
    "alibaba cloud",
}
_DATABASES = {
    "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
    "dynamodb", "sql", "nosql", "cassandra", "oracle", "mariadb", "sqlite",
    "snowflake", "bigquery", "redshift", "databricks", "firestore",
    "couchbase", "neo4j",
}
_DEVOPS_TOOLS = {
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "gitlab",
    "github actions", "circleci", "puppet", "chef", "helm", "argo cd",
    "prometheus", "grafana", "datadog", "splunk", "istio", "ecs", "eks",
    "cloudformation", "pulumi",
}
_AI_ML_TOOLS = {
    "tensorflow", "pytorch", "scikit-learn", "keras", "pandas", "numpy",
    "huggingface", "langchain", "openai", "llm", "llms", "nlp",
    "machine learning", "deep learning", "mlops", "generative ai",
    "computer vision", "spark", "hadoop", "airflow",
}
_METHODOLOGIES = {
    "agile", "scrum", "kanban", "waterfall", "safe", "lean", "tdd", "bdd",
    "devops", "ci/cd", "pair programming", "trunk-based development",
    "extreme programming", "sprint planning", "code review",
}
_SOFT_SKILLS_KEYWORDS = {
    "communication", "leadership", "collaboration", "mentoring",
    "mentorship", "stakeholder management", "problem-solving",
    "problem solving", "ownership", "cross-functional", "teamwork",
    "adaptability", "time management", "critical thinking",
    "attention to detail", "customer-focused", "self-starter",
}
_DOMAIN_KEYWORDS = {
    "fintech": "Fintech", "financial services": "Fintech", "banking": "Banking",
    "healthcare": "Healthcare", "health tech": "Healthcare", "healthtech": "Healthcare",
    "e-commerce": "E-commerce", "ecommerce": "E-commerce", "retail": "Retail",
    "saas": "SaaS", "logistics": "Logistics", "supply chain": "Logistics",
    "gaming": "Gaming", "insurance": "Insurance", "insurtech": "Insurance",
    "edtech": "Education", "education": "Education", "cybersecurity": "Cybersecurity",
    "telecom": "Telecom", "telecommunications": "Telecom", "travel": "Travel",
    "hospitality": "Travel", "real estate": "Real Estate", "proptech": "Real Estate",
    "media": "Media", "entertainment": "Media", "advertising": "AdTech",
    "adtech": "AdTech", "biotech": "Biotech", "pharma": "Biotech",
    "manufacturing": "Manufacturing", "energy": "Energy", "automotive": "Automotive",
    "government": "Government/Public Sector", "nonprofit": "Nonprofit",
}
_CERTIFICATION_RE = re.compile(
    r"\b("
    r"AWS\s+Certified\s+[A-Za-z][A-Za-z ]{2,40}|"
    r"Microsoft\s+Certified\s+[A-Za-z][A-Za-z ]{2,40}|"
    r"Azure\s+(?:Solutions\s+)?[A-Za-z][A-Za-z ]{2,30}?\s+Certif\w*|"
    r"Google\s+Cloud\s+Certified\s+[A-Za-z][A-Za-z ]{2,40}|"
    r"GCP\s+Certified\s+[A-Za-z][A-Za-z ]{2,40}|"
    r"PMP|CAPM|CSM|CSPO|PSM|PSPO|"
    r"CKA|CKAD|CKS|"
    r"CISSP|CISM|CISA|Security\+|CompTIA\s+\w+|"
    r"ITIL(?:\s+v?\d)?|"
    r"Certified\s+Scrum\s+Master|Certified\s+Kubernetes\s+[A-Za-z ]{2,30}"
    r")\b",
    re.IGNORECASE,
)
# Certification names captured above are greedy up to 40 chars and have no
# natural stopping point of their own, so they can swallow trailing JD
# filler words (e.g. "AWS Certified Solutions Architect preferred") -
# trimmed off in a second pass rather than fighting regex length limits.
_CERT_TRAILING_FILLER_RE = re.compile(
    r"\s+(?:preferred|required|desired|is\s+a\s+plus|a\s+plus|nice\s+to\s+have|"
    r"or\s+equivalent|equivalent)\.?\s*$",
    re.IGNORECASE,
)
_TITLE_PREFIX_RE = re.compile(r"^(?:job\s*title|position|role|title)\s*:\s*(.+)$", re.IGNORECASE)
_ROLE_WORD_RE = re.compile(
    r"\b(engineer|developer|manager|architect|analyst|designer|scientist|"
    r"lead|director|specialist|consultant|administrator|programmer)\b",
    re.IGNORECASE,
)
_QUALIFICATION_HINT_RE = re.compile(
    r"degree|bachelor|master|b\.?s\.?c?\b|m\.?s\.?c?\b|phd|certification|certified|years?\s+of\s+experience",
    re.IGNORECASE,
)

# Flat lookup for classifying keywords already extracted by ats_scorer as
# "named technology" vs. generic language (deliberately not exhaustive —
# just enough to usefully split step 5's prompt into technologies vs.
# generic required/preferred skill phrases). Kept as the union of every
# categorized dict above plus a few extras that don't need their own
# category, so resume_matcher's term collection stays comprehensive.
_TECHNOLOGY_TERMS = (
    _PROGRAMMING_LANGUAGES | _FRAMEWORKS | _CLOUD_PLATFORMS | _DATABASES
    | _DEVOPS_TOOLS | _AI_ML_TOOLS
    | {
        "kafka", "rabbitmq", "graphql", "grpc", "microservices", "git",
        "linux", "bash", "html", "css", "sass", "tailwind", "jira", "figma",
    }
)


def analyze_job_description(job_description: str) -> JdAnalysis:
    """Heuristic, AI-free JD analysis. Runs in low-single-digit
    milliseconds — pure regex/string work, no I/O."""
    keywords = sorted(_extract_keywords(job_description))
    technologies = sorted(k for k in keywords if k in _TECHNOLOGY_TERMS)

    lines = [line.strip() for line in job_description.splitlines()]
    required, preferred, responsibilities = _split_into_sections(lines)

    lower_text = job_description.lower()
    years_match = _YEARS_RE.search(job_description)

    return JdAnalysis(
        keywords=keywords,
        required_skills=required,
        preferred_skills=preferred,
        technologies=technologies,
        responsibilities=responsibilities,
        seniority=_detect_seniority(job_description),
        target_job_title=_detect_target_job_title(lines),
        programming_languages=_match_category(lower_text, keywords, _PROGRAMMING_LANGUAGES),
        frameworks=_match_category(lower_text, keywords, _FRAMEWORKS),
        cloud_platforms=_match_category(lower_text, keywords, _CLOUD_PLATFORMS),
        databases=_match_category(lower_text, keywords, _DATABASES),
        devops_tools=_match_category(lower_text, keywords, _DEVOPS_TOOLS),
        ai_ml_tools=_match_category(lower_text, keywords, _AI_ML_TOOLS),
        methodologies=_match_category(lower_text, keywords, _METHODOLOGIES),
        soft_skills=_match_category(lower_text, keywords, _SOFT_SKILLS_KEYWORDS),
        business_domain=_detect_business_domain(lower_text),
        qualifications=_detect_qualifications(required, preferred),
        certifications=_detect_certifications(job_description),
        required_years_experience=f"{years_match.group(1)}+ years" if years_match else "",
    )


_word_boundary_cache: dict[str, re.Pattern] = {}


def _term_present(term: str, lower_text: str) -> bool:
    """Word-boundary match, NOT a naive substring check - `"scala" in text`
    would false-positive-match inside "scalable", and single/short-letter
    vocabulary entries (e.g. "c", "r", "go") would match almost anywhere.
    Cached compiled patterns since the same curated vocabulary is checked
    against every job description."""
    pattern = _word_boundary_cache.get(term)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(term)}\b")
        _word_boundary_cache[term] = pattern
    return pattern.search(lower_text) is not None


def _match_category(lower_text: str, keywords: list[str], vocabulary: set[str]) -> list[str]:
    """Match a curated vocabulary against the JD via word-boundary search on
    the full lowercased text (catches multi-word terms like "google cloud"
    that single-token keyword extraction would miss, without the substring
    false positives a plain `in` check would produce) union'd with the
    already-tokenized keyword set (catches terms ats_scorer normalized
    slightly differently). Order: multi-word terms first (more specific),
    then alphabetical; capped at _MAX_ITEMS_PER_CATEGORY."""
    keyword_set = set(keywords)
    found = {term for term in vocabulary if term in keyword_set or _term_present(term, lower_text)}
    ordered = sorted(found, key=lambda t: (-len(t.split()), t))
    return ordered[:_MAX_ITEMS_PER_CATEGORY]


def _detect_target_job_title(lines: list[str]) -> str:
    for line in lines[:5]:
        if not line:
            continue
        match = _TITLE_PREFIX_RE.match(line)
        if match:
            return match.group(1).strip(" -–—")
    for line in lines[:3]:
        if line and len(line) <= 80 and _ROLE_WORD_RE.search(line):
            return line.strip(" -–—:")
    return ""


def _detect_business_domain(lower_text: str) -> str:
    for keyword, label in _DOMAIN_KEYWORDS.items():
        if keyword in lower_text:
            return label
    return ""


def _detect_qualifications(required: list[str], preferred: list[str]) -> list[str]:
    """Lines already captured under a required/preferred heading that read
    as formal qualifications (degree/certification/years) rather than pure
    tech-skill lines - a useful subset for summary framing, not a re-scan
    of the whole JD."""
    combined = required + preferred
    qualifications = [line for line in combined if _QUALIFICATION_HINT_RE.search(line)]
    return qualifications[:_MAX_ITEMS_PER_CATEGORY]


def _detect_certifications(job_description: str) -> list[str]:
    found = set()
    for m in _CERTIFICATION_RE.finditer(job_description):
        cleaned = _CERT_TRAILING_FILLER_RE.sub("", m.group(0).strip()).strip()
        if cleaned:
            found.add(cleaned)
    return sorted(found)[:_MAX_ITEMS_PER_CATEGORY]


def _split_into_sections(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    required: list[str] = []
    preferred: list[str] = []
    responsibilities: list[str] = []
    section: str | None = None

    for line in lines:
        if not line:
            continue
        if _REQUIRED_HEADING_RE.match(line):
            section = "required"
            continue
        if _PREFERRED_HEADING_RE.match(line):
            section = "preferred"
            continue
        if _RESPONSIBILITY_HEADING_RE.match(line):
            section = "responsibilities"
            continue
        if _OTHER_HEADING_RE.match(line):
            section = None
            continue

        if section is None:
            continue

        item = _BULLET_PREFIX_RE.sub("", line).strip()
        if not item or len(item) > 200:
            continue
        if section == "required":
            # "Experience with Kafka is a plus" under Requirements → preferred
            if _INLINE_PREFERRED_RE.search(item):
                preferred.append(item)
            else:
                required.append(item)
        elif section == "preferred":
            preferred.append(item)
        elif section == "responsibilities":
            responsibilities.append(item)

    # Cap lists — allow more preferred lines so nice-to-haves are not dropped.
    return (
        required[:_MAX_ITEMS_PER_CATEGORY],
        preferred[: max(_MAX_ITEMS_PER_CATEGORY, 20)],
        responsibilities[:_MAX_ITEMS_PER_CATEGORY],
    )


def _detect_seniority(text: str) -> str:
    years_match = _YEARS_RE.search(text)
    years = f"{years_match.group(1)}+ years" if years_match else ""

    for pattern, label in _SENIORITY_PATTERNS:
        if pattern.search(text):
            return f"{label} ({years})" if years else label

    return years or "Not specified"
