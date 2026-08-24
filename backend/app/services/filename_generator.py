"""Deterministic tailored-resume filename generation.

IMPORTANT (per the feature spec): filename generation must be deterministic
backend logic, NEVER an AI call - this is pure string sanitization, so the
same (candidate name, stack, company) always produces the exact same
filename, with zero latency/token cost and zero risk of the model
"helpfully" altering a company/candidate name.

Kept as its own small, reusable service (not inline in a route - see
.cursor/rules/resume-tailor-code-standards.mdc's "reusable services over
duplicated logic" rule) so app/api/routes/resume.py can call the exact same
function for the DOCX download, the PDF download, and the stored resume
history record, and any future export path stays automatically consistent.
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


def generate_resume_filename(
    candidate_name: str,
    main_stack: str,
    company_name: str,
    extension: str = "",
) -> str:
    """Build the deterministic filename:

        {Candidate Name}_{Main Stack}_{Company Name}[.{extension}]

    e.g. generate_resume_filename("Mateo Baranji", "Java", "Sequencer", "pdf")
         -> "Mateo Baranji_Java_Sequencer.pdf"

    Spaces WITHIN a component (e.g. a two-word candidate name) are kept as
    spaces - "_" is used only to join the three top-level components
    together, never as a stand-in for every space in the name.

    Never includes the job title or a timestamp (per spec) - only these
    three inputs, in this fixed order. Falls back to a generic base name
    only in the degenerate case where every component sanitizes to empty
    (e.g. all-symbol input) so callers always get a valid filename.
    """
    parts = [
        _sanitize_component(candidate_name),
        _sanitize_component(main_stack),
        _sanitize_component(company_name),
    ]
    base = "_".join(p for p in parts if p) or _DEFAULT_BASE_NAME

    extension = extension.strip().lstrip(".")
    return f"{base}.{extension}" if extension else base
