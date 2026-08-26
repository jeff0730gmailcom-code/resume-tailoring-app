"""Deterministic tailored-resume filename generation.

IMPORTANT (per the feature spec): filename generation must be deterministic
backend logic, NEVER an AI call - this is pure string sanitization, so the
same (candidate name, stack, company) always produces the exact same
names, with zero latency/token cost and zero risk of the model
"helpfully" altering a company/candidate name.

Kept as its own small, reusable service (not inline in a route - see
.cursor/rules/resume-tailor-code-standards.mdc's "reusable services over
duplicated logic" rule) so app/api/routes/resume.py can call the exact same
functions for the Downloads folder name, the CV file inside it, and the
stored resume history record.
"""
import re

# Everything outside letters, numbers, space, dot, hyphen, underscore is
# stripped - filesystem- and URL-safe by construction on every OS this runs
# on. Space is deliberately allowed WITHIN a component (see
# _sanitize_component) - only the join between components uses "_".
_DISALLOWED_CHARS_RE = re.compile(r"[^A-Za-z0-9 _.-]")
_WHITESPACE_RUN_RE = re.compile(r"\s+")
_UNDERSCORE_RUN_RE = re.compile(r"_+")
_DEFAULT_BASE_NAME = "Tailored_Resume"


def _sanitize_component(value: str) -> str:
    """Clean a single filename component:
    - collapse whitespace runs to a single space (spaces WITHIN a
      component, e.g. a two-word candidate name, are preserved as-is -
      only the separator BETWEEN the three components is an underscore,
      added by generate_resume_filename below)
    - strip any character that isn't a letter/number/space/dot/hyphen/
      underscore
    - collapse repeated underscores left behind by the step above
    - trim leading/trailing underscores/dots/spaces (e.g. "Acme Inc." ->
      "Acme Inc", not "Acme Inc." - the extension's own dot is added
      separately)

    Deliberately preserves the original casing - "use consistent
    capitalization" means never mangling case, not forcing upper/lower."""
    value = value.strip()
    value = _DISALLOWED_CHARS_RE.sub("", value)
    # Collapse whitespace AFTER stripping disallowed characters - otherwise
    # removing a symbol between two spaces (e.g. "React + Next.js" once "+"
    # is stripped) would leave a double space behind instead of one.
    value = _WHITESPACE_RUN_RE.sub(" ", value)
    value = _UNDERSCORE_RUN_RE.sub("_", value)
    return value.strip("_. ")


def generate_resume_folder_name(
    candidate_name: str,
    main_stack: str,
    company_name: str,
) -> str:
    """Build the deterministic export folder name:

        {Candidate Name}_{main stack}_{company name}

    e.g. generate_resume_folder_name("Mateo Baranji", "node", "robot")
         -> "Mateo Baranji_node_robot"

    Candidate name keeps original spacing and casing. Stack and company
    are lowercased so a typed "Node" / "Robot" still yields `_node_robot`.
    """
    parts = [
        _sanitize_component(candidate_name),
        _sanitize_component(main_stack).lower(),
        _sanitize_component(company_name).lower(),
    ]
    return "_".join(p for p in parts if p) or _DEFAULT_BASE_NAME


def generate_resume_cv_stem(candidate_name: str) -> str:
    """CV file name inside the export folder (no extension).

    e.g. generate_resume_cv_stem("Mateo Baranji") -> "Mateo Baranji"
    """
    return _sanitize_component(candidate_name) or "Resume"


def generate_resume_filename(
    candidate_name: str,
    main_stack: str,
    company_name: str,
    extension: str = "",
) -> str:
    """Stored export folder name.

    Historically this was a single download filename. Downloads now create
    a real folder named this way under the user's Downloads directory; the
    file inside is generate_resume_cv_stem plus .pdf/.docx. Optional
    extension is only for callers that still want a single-file name.
    """
    base = generate_resume_folder_name(candidate_name, main_stack, company_name)
    extension = extension.strip().lstrip(".")
    return f"{base}.{extension}" if extension else base
