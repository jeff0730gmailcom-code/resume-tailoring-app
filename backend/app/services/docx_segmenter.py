"""Heuristic structural segmentation of an uploaded DOCX master CV.

Used by app/services/cv_structurer.py to locate the *existing* paragraphs
in the candidate's own document that hold the summary, skills, each job's
header/bullets, and education - so the master CV's content can be parsed
into MasterCvData without re-deriving structure from raw text alone. The
parsed content is then tailored and rendered into a separately-selected
resume template (see app/services/template_renderer.py), independent of
the master CV's own original layout.

Walks every paragraph in the document via iter_all_paragraphs, including
ones inside table cells (recursively, for nested tables) - not just the
top-level body. Many real resume templates lay a sidebar/two-column layout
out using a table, and only ever reading document.paragraphs (python-docx's
default, top-level body only) would make the entire template invisible to
this segmenter, silently forcing cv_structurer to fall back to the
raw-text-only path instead of extracting proper structure - see
is_confident.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

_SUMMARY_HEADINGS = {
    "summary", "professional summary", "profile", "professional profile",
    "objective", "career objective", "about", "about me", "overview",
}
_SKILLS_HEADINGS = {
    "skill", "skills", "technical skills", "core competencies", "competencies",
    "technologies", "skills & tools", "skills and tools", "key skills",
    "skills & abilities", "skills and abilities",
}
_EXPERIENCE_HEADINGS = {
    "experience", "work experience", "employment", "employment history",
    "professional experience", "work history", "career history",
    "relevant experience", "professional background", "career",
    "employment record", "experience & education",
    "experience and education", "professional history",
}
_EDUCATION_HEADINGS = {
    "education", "academic background", "academic history", "qualifications",
}
# Preserved VERBATIM, never touched by AI or in-place editing - see
# cv_structurer._extract_raw_lines and app/prompts/resume_tailor_prompt.py's
# "never fabricate/remove a language or certification" rule.
_LANGUAGES_HEADINGS = {
    "languages", "language proficiency", "language skills", "spoken languages",
}
_CERTIFICATIONS_HEADINGS = {
    "certifications", "certificates", "licenses & certifications",
    "licenses and certifications", "certifications & licenses", "credentials",
}

_ALL_HEADINGS = (
    _SUMMARY_HEADINGS | _SKILLS_HEADINGS | _EXPERIENCE_HEADINGS | _EDUCATION_HEADINGS
    | _LANGUAGES_HEADINGS | _CERTIFICATIONS_HEADINGS
)

# \uf000-\uf0ff: the Private Use Area codepoints Word/PDF exporters commonly
# remap Wingdings/Symbol-font bullet glyphs to (e.g. \uf0b7 for a round
# bullet) - pypdf's text extraction preserves these as literal characters
# rather than resolving them to a normal "•", so plain-text bullet detection
# (see cv_structurer._merge_wrapped_bullets) needs this range too, not just
# the visible Unicode bullet glyphs.
BULLET_PREFIX_RE = re.compile(r"^\s*[•‣▪●◦○\-\*\uf000-\uf0ff]\s+")
_DATE_RANGE_RE = re.compile(
    r"(19|20)\d{2}.{0,15}(present|current|now|(19|20)\d{2})", re.IGNORECASE
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")
# Word-boundary / URL-ish only — bare "GitHub Actions" in a bullet must not
# count as a contact line (that previously stole Experience bullets into the
# contact detector when reused).
_CONTACT_HINT_RE = re.compile(
    r"(linkedin\.com|\blinkedin\b|github\.com|/portfolio\b|\bportfolio\b\s*:)",
    re.IGNORECASE,
)
# City/region lines like "Split, Croatia" or "Madrid, Spain".
_LOCATION_LIKE_RE = re.compile(
    r"^[A-Z][A-Za-z .'\-]+,\s*[A-Z][A-Za-z .'\-]+$",
)


@dataclass
class JobSegment:
    """One detected job entry: its non-bullet header line(s) and its bullet
    paragraphs, in original document order."""

    header_paragraphs: list[Paragraph] = field(default_factory=list)
    bullet_paragraphs: list[Paragraph] = field(default_factory=list)


@dataclass
class DocxSegments:
    summary_paragraphs: list[Paragraph] = field(default_factory=list)
    # True when summary_paragraphs came from an explicit Summary/Profile
    # heading — safe to rewrite in place. False when they were guessed from
    # preamble prose (still OK to rewrite those prose paragraphs only; name/
    # address/email lines are never placed here — see segment_document).
    summary_from_heading: bool = False
    skills_paragraphs: list[Paragraph] = field(default_factory=list)
    jobs: list[JobSegment] = field(default_factory=list)
    education_paragraphs: list[Paragraph] = field(default_factory=list)
    # Captured only so they're correctly excluded from every other section
    # (never misclassified as education/summary content).
    languages_paragraphs: list[Paragraph] = field(default_factory=list)
    certifications_paragraphs: list[Paragraph] = field(default_factory=list)

    @property
    def is_confident(self) -> bool:
        """Whether the segmentation found enough structure to safely drive
        in-place editing.         Only requires that at least one job entry was found at all - a job
        with no bullet lines is handled gracefully rather than failing the
        whole document's segmentation, since cv_structurer's raw-text
        fallback is far more lossy than accepting a partial structure."""
        return bool(self.jobs)

    @property
    def bullets_per_job(self) -> list[int]:
        """The master CV's own original per-job bullet paragraph counts.

        Not used as the AI's mandatory target bullet count - every job is
        regenerated to the fixed EXPERIENCE_BULLET_COUNT (see
        app/core/constants.py) regardless of the master CV's original
        count. Kept for informational/debugging purposes only."""
        return [len(job.bullet_paragraphs) for job in self.jobs]


def _heading_kind(text: str) -> str | None:
    normalized = text.strip().lower().strip(":")
    if not normalized or len(normalized) > 60:
        return None

    def _match(candidates: set[str]) -> bool:
        if normalized in candidates:
            return True
        # Allow "Experience (Selected)" / "Skills — Technical" style labels.
        return any(
            normalized.startswith(f"{c} ") or normalized.startswith(f"{c}(") or normalized.startswith(f"{c}—")
            or normalized.startswith(f"{c}-")
            for c in candidates
            if len(c) >= 4
        )

    if _match(_SUMMARY_HEADINGS):
        return "summary"
    if _match(_SKILLS_HEADINGS):
        return "skills"
    if _match(_EXPERIENCE_HEADINGS):
        return "experience"
    if _match(_EDUCATION_HEADINGS):
        return "education"
    if _match(_LANGUAGES_HEADINGS):
        return "languages"
    if _match(_CERTIFICATIONS_HEADINGS):
        return "certifications"
    return None


def _looks_like_heading(paragraph: Paragraph, text: str) -> bool:
    style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
    if "heading" in style_name or "title" in style_name:
        return _heading_kind(text) is not None
    return _heading_kind(text) is not None


def _looks_like_contact_line(text: str) -> bool:
    """Detect name/contact-block lines (email, phone, links, short location)
    that appear in the document header so they're never mistaken for summary
    and never overwritten by tailor_docx_in_place."""
    raw = text.strip()
    if not raw:
        return False
    if _EMAIL_RE.search(raw) or _PHONE_RE.search(raw) or _CONTACT_HINT_RE.search(raw):
        return True
    if raw.count("|") >= 1 and len(raw) < 120:
        return True
    # "Baranji \\tSplit, Croatia" / "Name\\tCity, Country"
    if "\t" in raw and len(raw) < 80:
        return True
    # Standalone short location line.
    if len(raw) <= 60 and _LOCATION_LIKE_RE.match(raw):
        return True
    # Very short non-prose header lines (first/last name alone) — never summary.
    if len(raw) <= 40 and "." not in raw and raw.count(" ") <= 2 and not any(ch.isdigit() for ch in raw):
        return True
    return False


def _looks_like_summary_prose(text: str) -> bool:
    """True for a real professional-summary paragraph (long prose), not a
    name/address/email header line."""
    raw = text.strip()
    if len(raw) < 80:
        return False
    if _looks_like_contact_line(raw):
        return False
    return raw.count(" ") >= 10


def _is_bullet_paragraph(paragraph: Paragraph, text: str) -> bool:
    style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
    if "bullet" in style_name or "list" in style_name:
        return True
    if BULLET_PREFIX_RE.match(text):
        return True
    try:
        p_pr = paragraph._p.pPr
        if p_pr is not None and p_pr.numPr is not None:
            return True
    except AttributeError:
        pass
    return False


def iter_all_paragraphs(document: DocumentObject) -> Iterator[Paragraph]:
    """Yield every paragraph in the document, in document order, descending
    into table cells (recursively, so nested tables are covered too) as
    well as the top-level body - unlike python-docx's own
    document.paragraphs, which only covers the top-level body. See module
    docstring for why this matters for table/sidebar-based CV templates."""
    yield from _iter_block_items(document.element.body, document, set())


def _iter_block_items(parent_elm, parent, seen_cell_ids: set[int]) -> Iterator[Paragraph]:
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            table = Table(child, parent)
            for row in table.rows:
                for cell in row.cells:
                    # A horizontally/vertically merged cell is returned once
                    # per grid column/row it spans by python-docx - skip
                    # repeats so its paragraphs aren't segmented twice.
                    if id(cell._tc) in seen_cell_ids:
                        continue
                    seen_cell_ids.add(id(cell._tc))
                    yield from _iter_block_items(cell._tc, cell, seen_cell_ids)


def segment_document(document: DocumentObject) -> DocxSegments:
    """Walk every paragraph in the document (top-level body and table
    cells - see iter_all_paragraphs) and classify them into summary /
    skills / per-job header+bullets / education buckets."""
    non_empty_paragraphs = [p for p in iter_all_paragraphs(document) if p.text.strip()]

    segments = DocxSegments()
    section: str | None = None
    current_job: JobSegment | None = None

    for paragraph in non_empty_paragraphs:
        text = paragraph.text.strip()

        heading_kind = _heading_kind(text) if _looks_like_heading(paragraph, text) else None
        if heading_kind:
            section = heading_kind
            current_job = None
            if heading_kind == "summary":
                segments.summary_from_heading = True
            continue

        if section is None:
            # Preamble before any section heading: name / address / email must
            # NEVER be classified as summary (a prior bug put "Baranji\\tSplit,
            # Croatia" into summary_paragraphs, then _apply_summary overwrote
            # it with the AI summary and wiped the real summary paragraph).
            if _looks_like_contact_line(text):
                continue
            if _looks_like_summary_prose(text):
                segments.summary_paragraphs.append(paragraph)
            continue

        if section == "summary":
            # Even under an explicit Summary heading, skip any stray contact
            # lines so address/email styles are never rewritten.
            if _looks_like_contact_line(text):
                continue
            segments.summary_paragraphs.append(paragraph)
        elif section == "skills":
            segments.skills_paragraphs.append(paragraph)
        elif section == "education":
            segments.education_paragraphs.append(paragraph)
        elif section == "languages":
            segments.languages_paragraphs.append(paragraph)
        elif section == "certifications":
            segments.certifications_paragraphs.append(paragraph)
        elif section == "experience":
            is_bullet = _is_bullet_paragraph(paragraph, text)
            if is_bullet:
                if current_job is None:
                    current_job = JobSegment()
                    segments.jobs.append(current_job)
                current_job.bullet_paragraphs.append(paragraph)
            else:
                if current_job is None or current_job.bullet_paragraphs:
                    current_job = JobSegment()
                    segments.jobs.append(current_job)
                current_job.header_paragraphs.append(paragraph)

    return segments
