"""Candidate-specific employer names (not AI-authored).

Identity facts normally come from the uploaded master CV. For Mateo
Baranji only, the experience companies are replaced with this fixed list
(most recent job first) so tailored output, cover letters, and answers
all see the same employers.
"""
from __future__ import annotations

import re

from app.models.schemas import MasterCvData

# (company, location) in CV order: newest role first.
MATEO_BARANJI_EMPLOYERS: tuple[tuple[str, str], ...] = (
    ("Talon.One", "Berlin, Germany"),
    ("Stream", "Amsterdam, Netherlands"),
    ("Tellent", "Amsterdam, Netherlands"),
    ("Codec", "Dublin, Ireland"),
    ("Scott Logic", "Newcastle upon Tyne, UK"),
)

_NAME_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_candidate_name(name: str) -> str:
    return _NAME_WHITESPACE_RE.sub(" ", (name or "").strip()).casefold()


def format_employer(company: str, location: str) -> str:
    """Single experience.company value shown on the resume."""
    company = company.strip()
    location = location.strip()
    if company and location:
        return f"{company}, {location}"
    return company or location


def _employer_labels(pairs: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(format_employer(company, location) for company, location in pairs)


def apply_candidate_employer_overrides(master_cv: MasterCvData) -> MasterCvData:
    """Rewrite Mateo Baranji job companies; leave every other CV unchanged."""
    if _normalize_candidate_name(master_cv.contact.name) != "mateo baranji":
        return master_cv
    if not master_cv.experience:
        return master_cv

    labels = _employer_labels(MATEO_BARANJI_EMPLOYERS)
    experience = list(master_cv.experience)
    raw_text = master_cv.raw_text
    replacements: list[tuple[str, str]] = []

    for index, new_company in enumerate(labels):
        if index >= len(experience):
            break
        entry = experience[index]
        old_company = entry.company.strip()
        experience[index] = entry.model_copy(update={"company": new_company})
        if old_company and old_company.casefold() != new_company.casefold():
            replacements.append((old_company, new_company))

    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    for old_company, new_company in replacements:
        raw_text = re.sub(re.escape(old_company), new_company, raw_text, flags=re.IGNORECASE)

    return master_cv.model_copy(update={"experience": experience, "raw_text": raw_text})
