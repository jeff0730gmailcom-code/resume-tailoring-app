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
            ["iBrain Technologies | Jul 2015 – Aug 2018", "Senior Full Stack Engineer"],
            "Senior Full Stack Engineer",
            "iBrain Technologies",
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


def test_structure_text_keeps_camel_case_employer():
    """Company-then-title headers like Sean Johnston's CV. A lowercase brand
    (iBrain) must not blank that job and force the unstructured AI path."""
    cv_text = """
Sean Johnston
seanjohnston896@gmail.com

SUMMARY
Senior Full Stack Engineer.

WORK EXPERIENCE
NextLink Labs | Nov 2022 – July 2026
Senior C# / .NET React Full Stack Engineer / Tech Lead
- Led development of enterprise platforms.
iBrain Technologies | Jul 2015 – Aug 2018
Senior Full Stack Engineer
- Delivered enterprise applications.
WheelHouse IT | July 2014 – June 2015
Software Engineer
- Developed full-stack web applications.
""".strip()
    structured = _structure_text(cv_text)
    assert structured is not None
    assert structured.is_structured
    assert [job.company for job in structured.experience] == [
        "NextLink Labs",
        "iBrain Technologies",
        "WheelHouse IT",
    ]
    assert structured.experience[1].title == "Senior Full Stack Engineer"
    assert "2015" in structured.experience[1].dates
    assert "2018" in structured.experience[1].dates


MARKO_STYLE_CV = """
Marko Baranji
Lajkovac, Serbia | markobaranjjin@gmail.com | +381 62 1495291

EDUCATION
Bachelor of Computer Science, University of Belgrade | 2009 to 2013

PROFESSIONAL EXPERIENCE
Self Employed
Senior Python Backend Engineer | Sep 2025 to Present
- Design Python backend and AI systems.
iPlena
Senior Python Backend Engineer | Dec 2022 to Nov 2025
- Architected Python backend services.
Sudonum Pty Ltd
Python Backend and Cloud Engineer | Jul 2020 to Nov 2022
- Built Django services.
Ingsoftware
Python Backend Engineer | Jan 2018 to Jul 2020
- Built backend microservices.
Codetribe
Backend Oriented Full Stack Engineer | Sep 2015 to Dec 2017
- Built portals.
Vega IT
Frontend Developer | Jun 2013 to Aug 2015
- Built web applications.

SELECTED PROJECT IMPACT
- Delivered production platforms across remote teams.
""".strip()


def test_structure_text_company_above_title_keeps_every_job_and_education():
    """Marko-style PDFs put the employer on the line above "Title | Dates",
    including a camel-case brand, and education above the jobs."""
    structured = _structure_text(MARKO_STYLE_CV)
    assert structured is not None
    assert structured.is_structured
    assert structured.contact.name == "Marko Baranji"
    assert structured.contact.email == "markobaranjjin@gmail.com"
    assert structured.contact.phone == "+381 62 1495291"
    assert structured.contact.location == "Lajkovac, Serbia"
    assert [(job.company, job.title, job.dates) for job in structured.experience] == [
        ("Self Employed", "Senior Python Backend Engineer", "Sep 2025 to Present"),
        ("iPlena", "Senior Python Backend Engineer", "Dec 2022 to Nov 2025"),
        ("Sudonum Pty Ltd", "Python Backend and Cloud Engineer", "Jul 2020 to Nov 2022"),
        ("Ingsoftware", "Python Backend Engineer", "Jan 2018 to Jul 2020"),
        ("Codetribe", "Backend Oriented Full Stack Engineer", "Sep 2015 to Dec 2017"),
        ("Vega IT", "Frontend Developer", "Jun 2013 to Aug 2015"),
    ]
    assert len(structured.education) == 1
    assert structured.education[0].degree == "Bachelor of Computer Science"
    assert structured.education[0].institution == "University of Belgrade"
    assert "2009" in structured.education[0].dates
    assert "2013" in structured.education[0].dates
    assert all("Delivered production platforms" not in bullet for job in structured.experience for bullet in job.bullets)


def test_structure_text_jobs_after_education_still_kept():
    """Stream order can place older employers after Education. They are still jobs."""
    cv_text = """
Marko Baranji
marko@example.com

PROFESSIONAL EXPERIENCE
Self Employed
Senior Python Backend Engineer | Sep 2025 to Present
- Design services.
iPlena
Senior Python Backend Engineer | Dec 2022 to Nov 2025
- Built APIs.
EDUCATION
Bachelor of Computer Science, University of Belgrade | 2009 to 2013
SELECTED PROJECT IMPACT
- Extra impact line that is not a job.
Ingsoftware
Python Backend Engineer | Jan 2018 to Jul 2020
- Built services.
Vega IT
Frontend Developer | Jun 2013 to Aug 2015
- Built interfaces.
""".strip()
    structured = _structure_text(cv_text)
    assert structured is not None
    assert [job.company for job in structured.experience] == [
        "Self Employed",
        "iPlena",
        "Ingsoftware",
        "Vega IT",
    ]
    assert structured.education[0].institution == "University of Belgrade"


def test_structure_text_reads_education_variants():
    cv_text = """
Ada Lovelace
ada@example.com

Academic Qualifications
B.Sc. Computer Science, University of Belgrade | 09.2009 - 07.2013

Experience
Analytical Engines | Jan 2014 – Present
Software Engineer
- Designed engines.
""".strip()
    structured = _structure_text(cv_text)
    assert structured is not None
    assert structured.is_structured
    assert structured.experience[0].company == "Analytical Engines"
    assert structured.education
    assert "2009" in structured.education[0].dates
    assert "2013" in structured.education[0].dates
    blob = f"{structured.education[0].degree} {structured.education[0].institution}".lower()
    assert "computer science" in blob
    assert "belgrade" in blob


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
