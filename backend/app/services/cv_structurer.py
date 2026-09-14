"""Convert a master CV into structured JSON — no AI involved.

This is "Step 1" of the pipeline: parse once at upload time, cache the
result, and let /tailor (and app/services/ai_tailor.py) work from compact
structured fields instead of re-sending the full raw CV text to the model
on every request.

Two structuring strategies, tried in order:
1. _structure_docx: paragraph/style-level segmentation (see
   app/services/docx_segmenter.py) for .docx uploads - the most reliable
   source of structure since paragraph styles/numbering survive.
2. _structure_text: plain-text line-level segmentation (heading keyword
   matching + job-boundary heuristics) for PDFs (which have no paragraph/
   style structure available from text extraction) and any .docx whose
   layout the paragraph-level pass couldn't confidently map.

Conservative by design: if neither strategy confidently maps the CV's
structure, or if any job's company name couldn't be reliably isolated (we
can never risk mangling a company name), MasterCvData.is_structured is left
False and raw_text is populated so app/services/ai_tailor.py falls back to
the original whole-document-text prompt path — never a hard failure.

Whichever strategy succeeds, cv_text is still always stored as raw_text so
callers always have that safety net available even for a structured result.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject

from app.models.schemas import ContactInfo, CvExperienceEntry, EducationEntry, MasterCvData
from app.services.docx_segmenter import (
    BULLET_PREFIX_RE,
    _CONTACT_HINT_RE,
    _EMAIL_RE,
    _LOCATION_LIKE_RE,
    _PHONE_RE,
    JobSegment,
    _heading_kind,
    _looks_like_heading,
    iter_all_paragraphs,
    segment_document,
    split_section_heading,
)
from app.services.employer_overrides import apply_candidate_employer_overrides
from app.services.text_sanitize import strip_broken_characters, strip_broken_from_tree

_SEPARATOR_RE = re.compile(r"\s*[-|–—@]\s*|\s*,\s*")
_LABEL_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z /&]{1,30}:\s*")
_SKILL_SPLIT_RE = re.compile(r"[,;|•/]")
# PDF extraction often prefixes a line with a bullet/replacement glyph
# ("□", U+FFFD, "Major:") that would otherwise leak into the rendered
# education/job fields as a broken square character.
_JUNK_PREFIX_RE = re.compile(
    r"^[\s\ufeff\ufffd\u25a0\u25a1\u25aa\u25ab\u25cf\u25e6\u2022•●◦○□■▪▫?\-]+\s*"
)
_MAJOR_PREFIX_RE = re.compile(r"^(major|degree|field of study)\s*:\s*", re.IGNORECASE)

# A more complete date-range matcher than docx_segmenter's (which only needs
# to *detect* a date range for heading classification). This one is used to
# *extract and strip* dates from a header/education line, so it must capture
# the whole span - including a leading month name - or stripping it would
# leave cruft like a dangling "Jan" stuck to the company name.
_MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-zA-Z]*\.?"
# Numeric month prefix ("09/", "2/") - handles "MM/YYYY" / "M/YYYY" date
# formats (e.g. "09/2023 - 2/2026"), not just "Month YYYY" / bare "YYYY".
_NUMERIC_MONTH_RE = r"(?:0?[1-9]|1[0-2])/"
_YEAR_SIDE_RE = rf"(?:{_MONTH_RE}\s+|{_NUMERIC_MONTH_RE})?(?:19|20)\d{{2}}"
_FULL_DATE_RANGE_RE = re.compile(
    rf"{_YEAR_SIDE_RE}\s*(?:[-–—]|to)\s*(?:{_YEAR_SIDE_RE}|present|current|now)",
    re.IGNORECASE,
)
# Bare "2", "2 of 3", "Page 2", "/ Page 2" - PDF page labels that must never
# become a fake employer or start a job (see Goran "Page 2" before Q Agency).
_PAGE_NOISE_RE = re.compile(
    r"^(?:[\/|.\-–—]*\s*)?(?:page\s+)?\d{1,3}(?:\s*(?:of|/)\s*\d{1,3})?(?:\s*[\/|.\-–—]*)?$",
    re.IGNORECASE,
)

# Common job-title role words - used to disambiguate which of two header
# lines is the title vs. the company when their order is reversed (e.g.
# "Company | Dates" then "Title", instead of the more common "Title" then
# "Company"). A company name only rarely contains one of these words, so
# this is a safe, low-risk heuristic rather than a strict rule.
_TITLE_KEYWORD_RE = re.compile(
    r"\b(engineer|developer|designer|manager|lead|architect|analyst|scientist|"
    r"specialist|consultant|director|officer|administrator|intern|coordinator|"
    r"strategist|producer|writer|marketer|recruiter|accountant|technician|"
    r"president|executive|founder|owner|principal|staff|senior|junior|head|"
    r"chief|cto|ceo|cfo|coo|vp|sre|swe|devops|fullstack|full[\s-]?stack)\b",
    re.IGNORECASE,
)
# Similarly disambiguates a degree line from an institution line when a
# 2-line education block's order can't be assumed (see _extract_education).
_DEGREE_KEYWORD_RE = re.compile(
    r"\b(bachelor|master|phd|doctorate|associate|diploma|degree|certificate|"
    r"bsc|msc|mba|b\.a\.|m\.a\.|b\.s\.|m\.s\.)\b",
    re.IGNORECASE,
)
# A single whitespace-free token that's clearly a phone number (e.g.
# "+381621897164" or "555-123-4567") - tried before the looser _PHONE_RE
# search across a whole line, because _PHONE_RE's char class allows
# whitespace *inside* the match, which would otherwise greedily swallow an
# adjacent, unrelated digit group on the same line (e.g. a postal code
# right after the phone number in a space-joined contact line extracted
# from a PDF, with no delimiter between them).
_PHONE_TOKEN_RE = re.compile(r"^\+?\(?\d[\d\-.()]{5,}\d\)?$")


def _is_name_only(text: str) -> bool:
    """True for a bare name fragment (e.g. a last name on its own header
    line) - never an email, location, or anything with a digit. Used to
    fold a name fragment on its own line into the full contact name
    rather than letting it fall through to location/email parsing.

    Deliberately False for anything that reads like a job-title tagline
    (e.g. "Senior Software Engineer" directly under the name) - short,
    comma-free, digit-free title lines would otherwise satisfy every other
    check here and get wrongly appended onto contact.name (producing a
    header like "JOHN DOE Senior Software Engineer"). That tagline isn't
    lost: templates that display a current-title line under the name
    already source it independently from experience[0].title (the most
    recent job) - see each template's "p.title"/"job-title" - which is
    also the correct fallback whenever the CV has no such header tagline
    at all. Templates that don't show a title line simply never reference
    it, so this line is intentionally dropped, not stored anywhere else."""
    raw = " ".join((text or "").split())
    if not raw or "@" in raw or "," in raw or _EMAIL_RE.search(raw):
        return False
    if _LOCATION_LIKE_RE.match(raw):
        return False
    if _TITLE_KEYWORD_RE.search(raw):
        return False
    return len(raw) <= 40 and raw.count(" ") <= 2 and not any(ch.isdigit() for ch in raw)


def split_title_company(text: str) -> tuple[str, str]:
    """Split a combined "Title / Company - Location" header line into
    (title, company) parts, preferring the last "/" that's followed by a
    location-style separator (a dash or comma) - handles titles that
    themselves contain a "/" (e.g. "Full Stack / Backend Engineer")."""
    raw = text.strip()
    matches = list(re.finditer(r"\s*/\s*", raw))
    if not matches:
        return raw, ""
    for match in reversed(matches):
        after = raw[match.end() :]
        if re.search(r"[–—-]", after) or "," in after:
            title = raw[: match.end()].rstrip()
            if not title.endswith("/"):
                title += " /"
            elif not title.endswith(" /"):
                title = title[:-1].rstrip() + " /"
            return title + (" " if not title.endswith(" ") else ""), after.lstrip()
    match = matches[0]
    title = raw[: match.end()].rstrip()
    if not title.endswith("/"):
        title += " /"
    return title + " ", raw[match.end() :].lstrip()


def _split_piped_title_company(text: str) -> tuple[str, str] | None:
    """Split a job header into (title, company).

    Prefer \"Title / Company\" (slash) when present — Dejan-style headers like
    \"Staff | Tech Lead Full Stack Engineer /TechBiz\" must keep the full title
    left of the slash. Pipe-splitting alone wrongly treated \"Tech Lead…\" as
    the employer.
    """
    raw = " ".join((text or "").split())
    if not raw:
        return None

    if "/" in raw:
        title_part, company_part = split_title_company(raw)
        title_part = title_part.rstrip(" /").strip()
        company_part = company_part.strip()
        if title_part and company_part and not _TITLE_KEYWORD_RE.search(company_part):
            return title_part, company_part

    parts = [p.strip() for p in re.split(r"\s*\|\s*", raw) if p.strip()]
    if len(parts) < 2:
        return None
    # Last segment is employer only when it does not look like another title bit.
    if _TITLE_KEYWORD_RE.search(parts[-1]) and not _looks_like_company_name(parts[-1]):
        return None
    return " | ".join(parts[:-1]), parts[-1]


def structure_cv(file_path: Path, cv_text: str, document: DocumentObject | None = None) -> MasterCvData:
    """Best-effort, AI-free structuring of a master CV.

    cv_text is always stored on the result (as raw_text) regardless of
    whether structuring succeeds, so callers always have a safe fallback."""
    cv_text = strip_broken_characters(cv_text or "")
    if file_path.suffix.lower() == ".docx":
        try:
            structured = _structure_docx(file_path, document)
        except Exception:  # noqa: BLE001 - structuring is best-effort, never fatal
            structured = None
        if structured is not None:
            return _finalize_master_cv(structured, cv_text)

    # Plain-text line-level structuring - the primary path for PDFs (no
    # paragraph/style structure survives PDF text extraction) and a safety
    # net for any .docx whose paragraph-level pass above wasn't confident.
    try:
        structured = _structure_text(cv_text)
    except Exception:  # noqa: BLE001 - structuring is best-effort, never fatal
        structured = None
    if structured is not None:
        return _finalize_master_cv(structured, cv_text)

    return _finalize_master_cv(
        MasterCvData(contact=ContactInfo(name="Unknown"), is_structured=False, raw_text=cv_text),
        cv_text,
    )


def _finalize_master_cv(structured: MasterCvData, cv_text: str) -> MasterCvData:
    """Strip extraction tofu from every field, then attach cleaned raw_text.

    If any experience entry is missing a usable title or company, mark the
    result unstructured so /tailor uses the safer raw-text path instead of
    locking blank/mangled headers into every tailored PDF.
    """
    data = strip_broken_from_tree(structured.model_dump())
    data["raw_text"] = cv_text
    result = apply_candidate_employer_overrides(MasterCvData.model_validate(data))
    if result.is_structured and not _experience_headers_reliable(result.experience):
        result.is_structured = False
    return result


def _experience_headers_reliable(experience: list[CvExperienceEntry]) -> bool:
    """True only when every job has a distinct non-empty title and company."""
    if not experience:
        return False
    for entry in experience:
        title = (entry.title or "").strip()
        company = (entry.company or "").strip()
        if not title or not company:
            return False
        if title.lower() == company.lower():
            return False
        # Soft-fill sometimes copies a full date-bearing header into company.
        if _FULL_DATE_RANGE_RE.search(company) and _TITLE_KEYWORD_RE.search(company):
            return False
    return True


def _structure_docx(file_path: Path, document: DocumentObject | None) -> MasterCvData | None:
    doc = document if document is not None else Document(str(file_path))
    segments = segment_document(doc)
    if not segments.is_confident:
        return None

    experience = [_parse_job_segment(job) for job in segments.jobs]
    # Only fill blank company from a *second* header line that looks like an
    # employer — never copy the title line into company (that locked mangled
    # headers into tailored PDFs for arbitrary CVs).
    for i, entry in enumerate(experience):
        if entry.company.strip():
            continue
        header_bits = [
            p.text.strip()
            for p in segments.jobs[i].header_paragraphs
            if p.text.strip()
        ]
        for bit in header_bits[1:]:
            candidate = clip_job_company(_clean_extracted_text(bit), entry.title)
            if candidate and candidate.lower() != (entry.title or "").lower():
                entry.company = candidate
                break

    if not _experience_headers_reliable(experience):
        return None

    return MasterCvData(
        contact=_extract_contact(doc),
        summary=" ".join(p.text.strip() for p in segments.summary_paragraphs if p.text.strip()),
        skills_raw=_extract_skills_raw([p.text for p in segments.skills_paragraphs]),
        experience=experience,
        education=_extract_education([p.text for p in segments.education_paragraphs]),
        languages_raw=_extract_raw_lines([p.text for p in segments.languages_paragraphs]),
        certifications_raw=_extract_raw_lines([p.text for p in segments.certifications_paragraphs]),
        is_structured=True,
    )


def _parse_job_segment(job: JobSegment) -> CvExperienceEntry:
    title, company, dates = _parse_job_header([p.text for p in job.header_paragraphs])
    bullets = [_clean_extracted_text(p.text) for p in job.bullet_paragraphs]
    bullets = [bullet for bullet in bullets if bullet]
    clipped_title = clip_job_title(title)
    company = clip_job_company(_clean_extracted_text(company), clipped_title)
    if not company and bullets and _looks_like_company_name(bullets[0]):
        company = clip_job_company(bullets[0], clipped_title)
        bullets = bullets[1:]
    return CvExperienceEntry(
        title=clipped_title,
        company=company,
        dates=_clean_extracted_text(dates),
        bullets=bullets,
    )


def _parse_job_header(header_lines: list[str]) -> tuple[str, str, str]:
    """Heuristically split a job's header line(s) into (title, company,
    dates). Handles common layouts: a standalone date-range line followed
    by one combined "Title / Company - Location" line (split via
    split_title_company above), two stacked lines in either order ("Title"
    / "Company" or "Company | Dates" / "Title" - disambiguated by
    _TITLE_KEYWORD_RE), and one combined line ("Title - Company | Dates")."""
    lines = [line.strip() for line in header_lines if line and line.strip()]
    if not lines:
        return "", "", ""

    combined = " | ".join(lines)
    date_match = _FULL_DATE_RANGE_RE.search(combined)
    dates = date_match.group(0).strip() if date_match else ""

    # Drop any line that's ENTIRELY a date range on its own (e.g.
    # "09/2023 - 2/2026" as its own header line) before splitting title/
    # company - otherwise a "date line" + "Title / Company" layout leaks
    # the date into the title (see the two-line branch below).
    content_lines = [line for line in lines if not _FULL_DATE_RANGE_RE.fullmatch(line)]
    if not content_lines:
        content_lines = lines

    if len(content_lines) >= 2:
        first = _FULL_DATE_RANGE_RE.sub("", content_lines[0]).strip(" |,-–—")
        second = _FULL_DATE_RANGE_RE.sub("", content_lines[1]).strip(" |,-–—")
        # Default: first line is the title (the common "Title" then
        # "Company" stacked layout). Only swap when the second line reads
        # like a job title and the first doesn't - handles the reversed
        # "Company | Dates" then "Title" layout some plain-text/PDF
        # resumes use, without disturbing the default for every other CV.
        if _TITLE_KEYWORD_RE.search(second) and not _TITLE_KEYWORD_RE.search(first):
            piped = _split_piped_title_company(second)
            if piped:
                return piped[0], piped[1], dates
            company = first if _looks_like_company_name(first) else ""
            return second, company, dates
        # Company sits on its own next line — keep the whole first line as
        # the title (including 'Title | specialty') rather than treating a
        # specialization as the employer. When PDF wraps \"/1648\" onto the
        # title and \"Factory\" onto the next line, rebuild \"1648 Factory\".
        if _looks_like_company_name(second):
            dangling = re.search(r"\s*/\s*(\d{2,5})\s*$", first)
            if dangling:
                title = first[: dangling.start()].strip(" |/-–—,") or first
                company = f"{dangling.group(1)} {second}".strip()
                return title, company, dates
            return first, second, dates
        piped = _split_piped_title_company(first)
        if piped:
            return piped[0], piped[1], dates
        return first, second, dates

    without_dates = _FULL_DATE_RANGE_RE.sub("", content_lines[0]).strip(" |,-–—")
    without_dates = " ".join(without_dates.split())

    # A company+dates-only line (e.g. "Engenious January 2025 - Present")
    # must never become the job title. Templates that show experience[0].title
    # under the candidate's name would otherwise print the employer there.
    if (
        without_dates
        and not _TITLE_KEYWORD_RE.search(without_dates)
        and _looks_like_company_name(without_dates)
    ):
        return "", without_dates, dates

    piped = _split_piped_title_company(without_dates)
    if piped:
        return piped[0], piped[1], dates

    # Single remaining line in "Title / Company - Location" shape - split
    # it with split_title_company (above) rather than the generic
    # separator split below (which would wrongly treat the whole "Title /
    # Company - Location" string as just the title).
    if "/" in without_dates:
        title_part, company_part = split_title_company(without_dates)
        title_part = title_part.rstrip(" /").strip()
        company_part = company_part.strip()
        if title_part and company_part:
            return title_part, company_part, dates

    parts = [p.strip() for p in _SEPARATOR_RE.split(without_dates) if p.strip()]
    title = parts[0] if parts else without_dates
    company = parts[1] if len(parts) > 1 else ""
    return title, company, dates


def _extract_contact(document: DocumentObject) -> ContactInfo:
    """Contact info lives in the first few lines of the document, before
    any section heading - scan only that window (stopping at the first
    recognized heading, capped at 6 lines regardless) so later content
    that coincidentally contains a comma or number is never mistaken for
    contact details."""
    raw_lines: list[str] = []
    for paragraph in iter_all_paragraphs(document):
        text = paragraph.text.strip()
        if not text:
            continue
        if _looks_like_heading(paragraph, text) and _heading_kind(text) is not None:
            break
        raw_lines.append(text)
        if len(raw_lines) >= 6:
            break
    return _extract_contact_from_lines(raw_lines, split_tabs=True)


def _extract_contact_from_lines(preamble_lines: list[str], *, split_tabs: bool = False) -> ContactInfo:
    """Shared contact-parsing core for both the DOCX (paragraph-derived)
    and plain-text (PDF/raw-text-derived) preambles.

    split_tabs handles a still tab-joined "Lastname\\tLocation" line (a Word
    PDF->DOCX conversion artifact) - not relevant for plain-text extraction,
    which never has literal tab characters in practice.

    Unlike the DOCX path (which classifies "|"-joined segments), plain-text
    preambles are frequently *space*-joined with no delimiter at all (e.g.
    "+381621897164 name@example.com City Country") - so email/phone are
    located anywhere in a line via regex search, then removed from that
    line, and whatever remains (if short enough) becomes the location.
    """
    raw_lines = [line for line in preamble_lines if line and line.strip()]
    if not raw_lines:
        return ContactInfo(name="Unknown")

    lines: list[str] = []
    for line in raw_lines:
        if split_tabs and "\t" in line:
            left, _, right = line.partition("\t")
            left, right = left.strip(), right.strip()
            if left:
                lines.append(left)
            if right:
                lines.append(right)
        else:
            lines.append(line)
    if not lines:
        return ContactInfo(name="Unknown")

    name = lines[0]
    idx = 1
    # Fold any immediately-following bare name-fragment line(s) - a last
    # name on its own line (header order: first name -> last name ->
    # location -> email) - into the full name instead of letting it fall
    # through to contact.location/email below (e.g. "Mateo" / "Baranji" /
    # "Split, Croatia" must become name="Mateo Baranji", not
    # location="Baranji" with "Split, Croatia" dropped).
    while idx < len(lines) and _is_name_only(lines[idx]):
        name = f"{name} {lines[idx]}".strip()
        idx += 1

    email = phone = location = linkedin = None
    for line in lines[idx:]:
        if line == name:
            continue
        remainder = line
        found_contact_detail = False

        if email is None:
            match = _EMAIL_RE.search(remainder)
            if match:
                email = match.group(0)
                remainder = (remainder[: match.start()] + remainder[match.end() :]).strip()
                found_contact_detail = True

        if phone is None:
            token_match = next((t for t in remainder.split() if _PHONE_TOKEN_RE.match(t.strip(",;"))), None)
            if token_match:
                phone = token_match.strip(",;")
                remainder = remainder.replace(token_match, "", 1).strip()
                found_contact_detail = True
            else:
                match = _PHONE_RE.search(remainder)
                if match:
                    phone = match.group(0).strip()
                    remainder = (remainder[: match.start()] + remainder[match.end() :]).strip()
                    found_contact_detail = True

        if linkedin is None and _CONTACT_HINT_RE.search(line):
            linkedin = line.strip()
            continue

        if location is not None:
            continue

        if found_contact_detail:
            # This line is proven to be a contact-detail line (it carried
            # an email or phone) - whatever's left over on it is safe to
            # treat as the location, even without a "City, Country" comma
            # (e.g. "11511 Obrenovac Serbia").
            candidate = remainder.strip(" |,-–—")
            if candidate and len(candidate) < 60 and "@" not in candidate:
                location = candidate
            continue

        # No email/phone found on this line - only accept it (or one of
        # its "|"-joined segments) as the location if it clearly reads
        # like one (e.g. "Split, Croatia"). Never a generic short line
        # (a role tagline like "Senior Engineer | React | Next.js" must
        # NOT be mistaken for a location just because it's short).
        for segment in line.split("|"):
            segment = segment.strip(" |,-–—")
            if segment and segment != name and _LOCATION_LIKE_RE.match(segment):
                location = segment
                break

    return ContactInfo(name=name, email=email, phone=phone, location=location, linkedin=linkedin)


def _merge_wrapped_skill_lines(lines: list[str]) -> list[str]:
    """Re-join skills-section lines a PDF's text extraction wrapped across
    two physical lines (see _merge_wrapped_bullets for why) - a genuinely
    new "Label: skill, skill" category line always starts with a label
    prefix, so any line that doesn't is assumed to be a continuation of
    the previous line and merged onto it, rather than becoming its own
    (nonsensical, label-less) entry."""
    merged: list[str] = []
    for line in lines:
        text = (line or "").strip()
        if not text:
            continue
        if merged and not _LABEL_PREFIX_RE.match(text):
            merged[-1] = f"{merged[-1]} {text}"
        else:
            merged.append(text)
    return merged


def _extract_skills_raw(skills_lines: list[str]) -> list[str]:
    """Flatten skills-block lines (which may be grouped under labels like
    "Languages: Python, JavaScript") into a deduplicated flat list of
    individual skill tokens.

    Callers with line-wrap-prone input (plain-text/PDF extraction - see
    _structure_text) must pre-merge wrapped lines with
    _merge_wrapped_skill_lines themselves before calling this - NOT done
    here unconditionally, since DOCX paragraphs (the other caller, see
    _structure_docx) are reliable, never-wrapped line boundaries where an
    unlabeled one-skill-per-paragraph layout must stay one token per line."""
    tokens: list[str] = []
    for line in skills_lines:
        text = _LABEL_PREFIX_RE.sub("", strip_broken_characters(line))
        for piece in _SKILL_SPLIT_RE.split(text):
            piece = strip_broken_characters(piece.strip(" ."))
            if piece and len(piece) < 40:
                tokens.append(piece)

    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(token)
    return deduped


def _extract_raw_lines(lines: list[str]) -> list[str]:
    """Verbatim text lines for sections that must never be touched or
    reworded (Languages, Certifications) - no parsing/splitting, unlike
    _extract_education, since these preserve exactly what the AI never
    sees and the backend splices straight through unchanged."""
    cleaned = [_clean_extracted_text(line) for line in lines]
    return [line for line in cleaned if line]


def _extract_education(education_lines: list[str]) -> list[EducationEntry]:
    """Parse Education-section lines into entries.

    A single institution's education info is often split across two lines
    (e.g. "University X | 2013-2016" then "Bachelor's Degree, Computer
    Science" on the next line) rather than packed into one - group lines
    into blocks starting at each date-bearing line (mirroring how job
    entries are grouped in _structure_text) instead of treating every
    line as its own separate entry, which would otherwise split one
    education record into two bogus half-entries.
    """
    lines = [line.strip() for line in education_lines if line and line.strip()]
    if not lines:
        return []

    blocks: list[list[str]] = []
    for line in lines:
        if not blocks:
            blocks.append([line])
            continue
        line_has_date = bool(_FULL_DATE_RANGE_RE.search(line))
        prev_has_date = any(_FULL_DATE_RANGE_RE.search(item) for item in blocks[-1])
        # A date line belongs to the previous school/degree block when that
        # block has no dates yet (common PDF layout: school/degree on one
        # line, "October 2011 - September 2016" on the next).
        if line_has_date and prev_has_date:
            blocks.append([line])
        else:
            blocks[-1].append(line)

    entries: list[EducationEntry] = []
    for block in blocks:
        combined = " | ".join(block)
        date_match = _FULL_DATE_RANGE_RE.search(combined)
        dates = date_match.group(0).strip() if date_match else ""

        remainder_parts = [
            _FULL_DATE_RANGE_RE.sub("", line).strip(" |,-–—()") for line in block
        ]
        remainder_parts = [part for part in remainder_parts if part]
        leftover = " ".join(remainder_parts).strip()
        # Skip leftover "Bachelor :" / "Master :" year-only rows when the
        # main school/degree line was already captured.
        if leftover and re.match(r"^(bachelor|master)\s*:?\s*$", leftover, re.IGNORECASE):
            continue

        degree, institution = _split_degree_institution(remainder_parts)

        entries.append(
            EducationEntry(
                degree=_clean_extracted_text(degree),
                institution=_clean_extracted_text(institution),
                dates=_clean_extracted_text(dates),
            )
        )
    return entries


def _split_degree_institution(remainder_parts: list[str]) -> tuple[str, str]:
    """Pick degree vs school from one or more leftover education fragments."""
    if not remainder_parts:
        return "", ""
    if len(remainder_parts) >= 2:
        first, second = remainder_parts[0], remainder_parts[1]
        if _DEGREE_KEYWORD_RE.search(second) and not _DEGREE_KEYWORD_RE.search(first):
            return second, first
        return first, second

    remainder = remainder_parts[0]
    parts = [p.strip() for p in _SEPARATOR_RE.split(remainder) if p.strip()]
    if not parts:
        return remainder, ""
    degree_hit = next((p for p in parts if _DEGREE_KEYWORD_RE.search(p)), None)
    uni_hit = next(
        (p for p in parts if re.search(r"\b(university|college|school|institute)\b", p, re.IGNORECASE)),
        None,
    )
    if degree_hit or uni_hit:
        return degree_hit or parts[0], uni_hit or ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def _clean_extracted_text(text: str) -> str:
    """Strip PDF-extraction junk (replacement chars, bullet glyphs, a
    leading 'Major:' label) so templates never render a broken square or
    a packed 'Major: … | DEGREE | SCHOOL' line."""
    cleaned = strip_broken_characters(text)
    cleaned = _JUNK_PREFIX_RE.sub("", cleaned)
    cleaned = _MAJOR_PREFIX_RE.sub("", cleaned)
    return strip_broken_characters(cleaned.strip(" |,-–—"))


_ACTION_VERBS = (
    "Designed|Architected|Developed|Built|Implemented|Led|Created|"
    "Owned|Managed|Improved|Optimized|Engineered|Delivered|Launched|"
    "Established|Introduced|Drove|Spearheaded|Conducted|Collaborated"
)
_ACTION_VERB_RE = re.compile(rf"\s+(?=(?:{_ACTION_VERBS})\b)", re.IGNORECASE)
_DUTY_START_RE = re.compile(rf"^(?:{_ACTION_VERBS})\b", re.IGNORECASE)


def clip_job_title(title: str, max_len: int = 120) -> str:
    """Keep the job title itself — never a duty/description sentence.

    Preserve pipe specializations (\"Staff | Tech Lead Full Stack Engineer\")
    when both sides look like title fragments. Only drop a long trailing
    clause that clearly starts a duty sentence.
    """
    title = strip_broken_characters(title)
    title = " ".join(title.replace("\n", " ").split())
    title = _JUNK_PREFIX_RE.sub("", title)
    # Strip a glued duty sentence after the title, but not \"Staff | Tech Lead\".
    duty_split = _ACTION_VERB_RE.split(title, maxsplit=1)
    if len(duty_split) > 1 and _TITLE_KEYWORD_RE.search(duty_split[0]):
        title = duty_split[0].strip(" |/-–—,")
    if _DUTY_START_RE.match(title):
        return ""
    if " | " in title:
        left, right = title.split(" | ", 1)
        # Drop only when the right side is a long lowercase duty phrase.
        if right and right[:1].islower() and len(right) > 40 and not _TITLE_KEYWORD_RE.search(right):
            title = left.strip()
    if len(title) > max_len:
        title = title[:max_len].rsplit(" ", 1)[0].strip(" |/-–—,")
    return strip_broken_characters(title)


def clip_job_company(company: str, title: str = "", max_len: int = 80) -> str:
    """Keep a short employer name. Drop glued duty sentences and dates.

    Never drop a company merely because it also appears inside a combined
    title (\"Senior Engineer | Netguru\") — missing company is worse than a
    duplicated fragment, and templates need the employer field.
    """
    company = strip_broken_characters(company)
    company = " ".join(company.replace("\n", " ").split())
    company = _JUNK_PREFIX_RE.sub("", company)
    if not company:
        return ""
    if _DUTY_START_RE.match(company):
        return ""
    # Dates belong in the dates field. A "Company January 2025 - Present"
    # leftover (common when PDF extraction glues employer + dates on one
    # line) must not render as the company name beside the real dates.
    company = _FULL_DATE_RANGE_RE.sub("", company).strip(" |/-–—,")
    company = " ".join(company.split())
    company = _ACTION_VERB_RE.split(company, maxsplit=1)[0].strip(" |/-–—,")
    if _DUTY_START_RE.match(company) or len(company) > max_len:
        return ""
    # Only suppress when company is identical to the whole title (soft-fill bug).
    if title and company.lower() == title.lower():
        return ""
    return strip_broken_characters(company)


def _looks_like_company_name(text: str) -> bool:
    """True for a short employer line sitting under a title/dates header
    (e.g. "TechNova", "GlobalSoft Systems", "1648 Factory", "Lead Bank").

    Rejects duty sentences and full job-title lines, but allows employers
    that merely contain a role word (\"Lead Bank\", \"Engineer.ai\").
    """
    raw = " ".join((text or "").split())
    if not raw or len(raw) > 60:
        return False
    if _PAGE_NOISE_RE.match(raw):
        return False
    if BULLET_PREFIX_RE.match(raw) or _FULL_DATE_RANGE_RE.search(raw):
        return False
    if _DUTY_START_RE.match(raw):
        return False
    if _looks_like_standalone_job_title(raw):
        return False
    if raw[:1].islower():
        return False
    return raw.count(" ") <= 5 and not raw.endswith((".", ";"))


def _looks_like_standalone_job_title(line: str) -> bool:
    """True for a job-title line that sits ABOVE the company+dates line
    (e.g. "Tech Lead Devops & Cloud Engineer" then "Engenious January
    2025 - Present"). Date-bearing lines are job boundaries, not titles;
    duty/bullet sentences are not titles either."""
    raw = " ".join((line or "").split())
    if not raw or len(raw) > 100:
        return False
    if BULLET_PREFIX_RE.match(raw) or _FULL_DATE_RANGE_RE.search(raw):
        return False
    if _DUTY_START_RE.match(raw) or not _TITLE_KEYWORD_RE.search(raw):
        return False
    if raw.endswith((".", ";", ",")):
        return False
    words = raw.replace("/", " ").replace("|", " ").replace("&", " ").split()
    return 1 < len(words) <= 14 and raw.count(",") <= 1


def _looks_like_company_date_header(line: str) -> bool:
    """True for "Engenious January 2025 - Present": employer + date range
    on one line, which must stay a header (not a bullet) when the title
    is the line above it."""
    raw = " ".join((line or "").split())
    if not raw or not _FULL_DATE_RANGE_RE.search(raw):
        return False
    remainder = _FULL_DATE_RANGE_RE.sub("", raw).strip(" |,-–—")
    remainder = " ".join(remainder.split())
    return bool(remainder) and _looks_like_company_name(remainder)


def _looks_like_combined_job_header(line: str) -> bool:
    """True for a one-line "Title | Company | Dates" / "Title | Dates"
    header. That line must stay in the header even when a junk fragment
    (page label, wrapped word) was prepended as the first job line."""
    raw = " ".join((line or "").split())
    if not raw or not _FULL_DATE_RANGE_RE.search(raw):
        return False
    remainder = _FULL_DATE_RANGE_RE.sub("", raw).strip(" |,-–—")
    remainder = " ".join(remainder.split())
    return bool(remainder) and bool(_TITLE_KEYWORD_RE.search(remainder) or "|" in raw)


def _looks_like_trailing_employer(line: str) -> bool:
    """Employer sitting above the next job's date line.

    Includes single-token employers (Factory, Globant) that PDF extraction
    parks on their own line under \"Title /1648\".
    """
    if not _looks_like_company_name(line):
        return False
    raw = " ".join(line.split())
    if " " in raw or raw.isupper():
        return True
    if re.match(r"^[A-Z][a-zA-Z]*[A-Z][a-zA-Z0-9]+$", raw):
        return True
    if re.match(r"^[A-Z][A-Za-z0-9&.'-]{1,40}$", raw) and not _TITLE_KEYWORD_RE.search(raw):
        return True
    return False


def _looks_like_trailing_job_header(line: str) -> bool:
    """A title or company line parked at the end of the previous job."""
    if _looks_like_job_boundary(line) or _PAGE_NOISE_RE.match(line.strip()):
        return False
    if _looks_like_standalone_job_title(line) or _looks_like_trailing_employer(line):
        return True
    raw = " ".join((line or "").split())
    if (
        raw
        and _TITLE_KEYWORD_RE.search(raw)
        and ("|" in raw or "/" in raw)
        and not BULLET_PREFIX_RE.match(raw)
    ):
        return True
    return False


def _looks_like_job_boundary(line: str) -> bool:
    """True for a line that starts a new job entry inside the Experience
    section of a plain-text CV: contains a full date range and reads like
    a header rather than a bullet sentence - e.g. "Netguru | Sep 2023 -
    May 2026" or "Senior Engineer, Acme Corp (2019-2022)".

    Also matches "Title | May 2023 – February 2026" (company often on the
    next line). Bullets that happen to mention two years (rare) are
    excluded by requiring the line to be reasonably short and not end in
    sentence punctuation - real header lines practically never end with
    a period/semicolon."""
    if _PAGE_NOISE_RE.match(line.strip()):
        return False
    if not _FULL_DATE_RANGE_RE.search(line):
        return False
    return len(line) < 160 and not line.rstrip().endswith((".", ";"))


def _is_standalone_date_line(line: str) -> bool:
    """True when the line is only a date range (Dejan PDF: title, Factory, then dates)."""
    raw = " ".join((line or "").split())
    if not raw:
        return False
    return bool(_FULL_DATE_RANGE_RE.fullmatch(raw))


def _is_header_continuation(line: str) -> bool:
    """True for a non-bullet line that still belongs in the job header."""
    nxt = (line or "").strip()
    if not nxt or len(nxt) >= 160:
        return False
    if BULLET_PREFIX_RE.match(nxt) or _DUTY_START_RE.match(nxt):
        return False
    if _is_standalone_date_line(nxt):
        return True
    if _looks_like_company_date_header(nxt) or _looks_like_combined_job_header(nxt):
        return True
    if _FULL_DATE_RANGE_RE.search(nxt):
        return False
    return (
        _looks_like_company_name(nxt)
        or _looks_like_standalone_job_title(nxt)
        or _looks_like_trailing_employer(nxt)
    )


def _split_job_header_and_bullets(job_lines: list[str]) -> tuple[list[str], list[str]]:
    """Split one job's raw lines into header line(s) and bullet lines.

    Takes up to three leading header lines so stacked PDF layouts work:
    \"Title /1648\", \"Factory\", \"JANUARY 2022 – JANUARY 2023\".
    Duty/bullet lines stay bullets.
    """
    if not job_lines:
        return [], []
    header = [job_lines[0]]
    rest = job_lines[1:]
    while rest and len(header) < 3 and _is_header_continuation(rest[0]):
        header.append(rest[0])
        rest = rest[1:]
    return header, rest


def _merge_wrapped_bullets(bullet_lines: list[str]) -> list[str]:
    """Re-join bullet lines that a PDF's text extraction wrapped across two
    (or more) physical lines back into a single logical bullet.

    pypdf's text extraction emits one "line" per physical line of the
    rendered page, so a long bullet that wraps onto a second visual line in
    the PDF comes back as two separate lines with no punctuation telling
    them apart from a genuinely new bullet - EXCEPT that only the true
    start of a bullet carries its marker character (a plain "-"/"•", or a
    Symbol/Wingdings-font glyph like the common "\uf0b7", which PDF text
    extraction preserves as a literal Private Use Area character - see
    docx_segmenter.BULLET_PREFIX_RE). A wrapped continuation line never
    repeats that marker.

    This only kicks in when at least one line in this job's bullets
    visibly uses such a marker - detected fresh per job, never assumed -
    so a resume with genuinely one-bullet-per-line and no marker at all
    (the common case when a line never wraps) is left untouched: every
    line stays its own bullet exactly as before.
    """
    lines = [line for line in bullet_lines if line and line.strip()]
    if not lines:
        return []
    if not any(BULLET_PREFIX_RE.match(line) for line in lines):
        return [line.strip() for line in lines]

    merged: list[str] = []
    for line in lines:
        if BULLET_PREFIX_RE.match(line) or not merged:
            merged.append(BULLET_PREFIX_RE.sub("", line).strip())
        else:
            merged[-1] = f"{merged[-1]} {line.strip()}".strip()
    return [bullet for bullet in merged if bullet]


def _structure_text(cv_text: str) -> MasterCvData | None:
    """Plain-text line-level structuring - the primary structuring path for
    PDF uploads (which have no paragraph/style structure available from
    text extraction, unlike DOCX - see _structure_docx) and a fallback for
    any .docx the paragraph-level pass above couldn't confidently map.

    Groups lines under the same section-heading keywords as
    docx_segmenter._heading_kind (reused as-is since it's purely
    text-based), and within the Experience section, splits jobs at each
    date-range-bearing header line (see _looks_like_job_boundary) rather
    than relying on bullet/numbering formatting, which plain extracted
    text never preserves. When the title sits on the line above a
    company+dates boundary (a common PDF layout), that title is attached
    to the new job rather than dropped or left as the previous job's last
    bullet.

    Returns None (never raises) when no job entries could be confidently
    located, so structure_cv falls back to the raw-text AI path exactly
    like an unconfident DOCX segmentation does.
    """
    lines = [line.strip() for line in (cv_text or "").splitlines() if line.strip()]
    if not lines:
        return None

    preamble: list[str] = []
    summary_lines: list[str] = []
    skills_lines: list[str] = []
    education_lines: list[str] = []
    languages_lines: list[str] = []
    certifications_lines: list[str] = []
    jobs: list[list[str]] = []
    current_job: list[str] | None = None
    pending_header_lines: list[str] = []
    section: str | None = None

    for line in lines:
        if _PAGE_NOISE_RE.match(line):
            continue

        heading, remainder = split_section_heading(line)
        if heading:
            section = heading
            current_job = None
            pending_header_lines = []
            if not remainder:
                continue
            line = remainder

        if section is None:
            preamble.append(line)
            continue

        if section == "summary":
            summary_lines.append(line)
        elif section == "skills":
            skills_lines.append(line)
        elif section == "education":
            education_lines.append(line)
        elif section == "languages":
            languages_lines.append(line)
        elif section == "certifications":
            certifications_lines.append(line)
        elif section == "experience":
            if _looks_like_job_boundary(line):
                stolen: list[str] = []
                if current_job:
                    # Title (and a bare company name) sit on the line(s)
                    # ABOVE "Company January 2025 - Present". The date line
                    # is the only boundary, so those lines were appended to
                    # the previous job; pull them back.
                    while len(current_job) > 1 and _looks_like_trailing_job_header(current_job[-1]):
                        stolen.append(current_job.pop())
                    stolen.reverse()
                elif pending_header_lines:
                    stolen = [
                        item
                        for item in pending_header_lines
                        if _looks_like_standalone_job_title(item) or _looks_like_company_name(item)
                    ]
                pending_header_lines = []
                current_job = stolen + [line]
                jobs.append(current_job)
            elif current_job is not None:
                current_job.append(line)
            elif _looks_like_standalone_job_title(line) or _looks_like_company_name(line):
                pending_header_lines.append(line)

    if not jobs:
        return None

    experience: list[CvExperienceEntry] = []
    job_header_lines: list[list[str]] = []
    for job_lines in jobs:
        header_lines, bullet_lines = _split_job_header_and_bullets(job_lines)
        job_header_lines.append(header_lines)
        title, company, dates = _parse_job_header(header_lines)
        bullets = [_clean_extracted_text(bullet) for bullet in _merge_wrapped_bullets(bullet_lines)]
        bullets = [bullet for bullet in bullets if bullet]
        clipped_title = clip_job_title(title)
        company = clip_job_company(_clean_extracted_text(company), clipped_title)
        if not company and bullets and _looks_like_company_name(bullets[0]):
            company = clip_job_company(bullets[0], clipped_title)
            bullets = bullets[1:]
        experience.append(
            CvExperienceEntry(
                title=clipped_title,
                company=company,
                dates=_clean_extracted_text(dates),
                bullets=bullets,
            )
        )

    # Only fill blank company from a later header line that looks like an
    # employer — never copy the title line into company.
    for i, entry in enumerate(experience):
        if entry.company.strip():
            continue
        for bit in job_header_lines[i][1:]:
            candidate = clip_job_company(_clean_extracted_text(bit), entry.title)
            if candidate and candidate.lower() != (entry.title or "").lower():
                entry.company = candidate
                break

    if not _experience_headers_reliable(experience):
        return None

    return MasterCvData(
        contact=_extract_contact_from_lines(preamble),
        summary=" ".join(summary_lines),
        skills_raw=_extract_skills_raw(_merge_wrapped_skill_lines(skills_lines)),
        experience=experience,
        education=_extract_education(education_lines),
        languages_raw=_extract_raw_lines(languages_lines),
        certifications_raw=_extract_raw_lines(certifications_lines),
        is_structured=True,
    )
