"""Regression tests: job title/company parsing must work for arbitrary CV shapes."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.cv_structurer import (  # noqa: E402
    _experience_headers_reliable,
    _parse_job_header,
    _structure_text,
    clip_job_company,
    clip_job_title,
)
from app.models.schemas import CvExperienceEntry  # noqa: E402


@pytest.mark.parametrize(
    "header_lines, expected_title, expected_company",
    [
        (
            ["Staff | Tech Lead Full Stack Engineer /TechBiz", "FEBRUARY 2023 – MAY 2026"],
            "Staff | Tech Lead Full Stack Engineer",
            "TechBiz",
        ),
        (
            [
                "Staff Software Engineer | Tech Lead (.NET, Cloud & Full Stack) /1648",
                "Factory",
                "JANUARY 2022 – JANUARY 2023",
            ],
            "Staff Software Engineer | Tech Lead (.NET, Cloud & Full Stack)",
            "1648 Factory",
        ),
        (
            ["Senior Full Stack .NET Engineer | DBB Software", "MAY 2018 – DECEMBER 2021"],
            "Senior Full Stack .NET Engineer",
            "DBB Software",
        ),
        (
            ["Backend Engineer | DevOps Engineer (.NET & Cloud)/ DBB Software", "MARCH 2016 – APRIL 2018"],
            "Backend Engineer | DevOps Engineer (.NET & Cloud)",
            "DBB Software",
        ),
        (
            ["CTO", "Acme Corp", "Jan 2020 – Present"],
            "CTO",
            "Acme Corp",
        ),
        (
            ["Principal Software Engineer / Lead Bank", "2021 – 2024"],
            "Principal Software Engineer",
            "Lead Bank",
        ),
    ],
)
def test_parse_job_header_shapes(header_lines, expected_title, expected_company):
    title, company, dates = _parse_job_header(header_lines)
    title = clip_job_title(title)
    company = clip_job_company(company, title)
    assert title == expected_title
    assert company == expected_company
    assert dates


def test_clip_job_company_keeps_employer_also_in_title():
    title = "Senior Engineer | Netguru"
    assert clip_job_company("Netguru", title) == "Netguru"


def test_experience_headers_reject_blank_or_duplicated():
    assert not _experience_headers_reliable([])
    assert not _experience_headers_reliable(
        [CvExperienceEntry(title="", company="Acme", dates="2020", bullets=[])]
    )
    assert not _experience_headers_reliable(
        [CvExperienceEntry(title="Engineer", company="Engineer", dates="2020", bullets=[])]
    )
    assert _experience_headers_reliable(
        [CvExperienceEntry(title="Engineer", company="Acme", dates="2020", bullets=[])]
    )


def test_structure_text_dejan_style_preserves_all_titles():
    cv_text = """
Dejan Pavlovic
dejan@example.com

Summary
Senior Full Stack Engineer with 10+ years.

Experience
Staff | Tech Lead Full Stack Engineer /TechBiz FEBRUARY 2023 – MAY 2026
- Led design of platform services
Staff Software Engineer | Tech Lead (.NET, Cloud & Full Stack) /1648
Factory
JANUARY 2022 – JANUARY 2023
- Built cloud services
Tech Lead Full Stack Engineer (C# | .NET, React & Cloud) /1648
Factory
JANUARY 2020 – DECEMBER 2021
- Implemented APIs
Senior Full Stack .NET Engineer | DBB Software MAY 2018 – DECEMBER 2021
- Developed products
Backend Engineer | DevOps Engineer (.NET & Cloud)/ DBB Software MARCH 2016 – APRIL 2018
- Containerized backend services
""".strip()
    structured = _structure_text(cv_text)
    assert structured is not None
    assert structured.is_structured
    assert len(structured.experience) == 5
    assert structured.experience[0].title == "Staff | Tech Lead Full Stack Engineer"
    assert structured.experience[0].company == "TechBiz"
    assert structured.experience[1].title.startswith("Staff Software Engineer")
    assert structured.experience[1].company == "1648 Factory"
    assert structured.experience[1].dates
    assert structured.experience[2].title.startswith("Tech Lead Full Stack Engineer")
    assert structured.experience[2].company == "1648 Factory"
    assert structured.experience[2].dates


def test_structure_text_rejects_jobs_without_company():
    cv_text = """
Jane Doe
jane@example.com

Experience
Mystery Role JANUARY 2020 – DECEMBER 2021
- Did things without a company line
""".strip()
    # Single mangled header may parse company empty → quality gate returns None
    structured = _structure_text(cv_text)
    assert structured is None or not _experience_headers_reliable(structured.experience)
