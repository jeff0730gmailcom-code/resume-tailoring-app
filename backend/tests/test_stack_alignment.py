"""Regression: tailored experience must stay on the application main stack."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.schemas import (  # noqa: E402
    ContactInfo,
    CvExperienceEntry,
    ExperienceEntry,
    MasterCvData,
    SkillCategories,
    TailoredResumeContent,
)
from app.services.resume_validator import validate_and_fix_resume  # noqa: E402
from app.services.stack_alignment import (  # noqa: E402
    competing_families_in_text,
    resolve_stack_family,
    rewrite_toward_stack,
    sanitize_title_for_stack,
)


def test_resolve_dotnet_stack_variants():
    for label in (".NET", "dotnet", "C#", "ASP.NET Core"):
        family = resolve_stack_family(label)
        assert family is not None
        assert family.key == "dotnet"


def test_php_is_competing_with_dotnet():
    primary = resolve_stack_family(".NET")
    assert primary is not None
    rivals = competing_families_in_text(
        "Developed RESTful endpoints in Laravel and PHP for 8 features.",
        primary,
    )
    assert any(r.key == "php" for r in rivals)


def test_rewrite_php_toward_dotnet():
    primary = resolve_stack_family("dotnet")
    assert primary is not None
    text = "Developed RESTful endpoints in Laravel and PHP, with PHPUnit coverage for 10 modules."
    cleaned = rewrite_toward_stack(text, primary)
    lower = cleaned.lower()
    assert "php" not in lower
    assert "laravel" not in lower
    assert "phpunit" not in lower
    assert "c#" in lower or ".net" in lower or "asp.net" in lower


def test_sanitize_php_title_for_dotnet():
    primary = resolve_stack_family(".NET")
    assert primary is not None
    cleaned = sanitize_title_for_stack("Junior PHP / Laravel Developer", primary)
    lower = cleaned.lower()
    assert "php" not in lower
    assert "laravel" not in lower
    assert "junior" in lower
    assert "developer" in lower


def test_validator_rewrites_php_junior_for_dotnet_application():
    tailored = TailoredResumeContent(
        contact=ContactInfo(name="Stefan Stepic"),
        summary="Senior Backend Engineer focused on C#/.NET.",
        skills=SkillCategories(languages=["C#"], backend=[".NET"]),
        experience=[
            ExperienceEntry(
                title="Tech Lead / Software Engineer",
                company="Future Processing",
                dates="07/2017 – 09/2021",
                bullets=[
                    "Led design and delivery of .NET Core microservices with PostgreSQL for 6 modules.",
                    "Architected message-based integration with Kafka and RabbitMQ, increasing capacity by 3x.",
                    "Established TDD practices, raising coverage from 28% to 78% across a 9-person squad.",
                    "Designed secure API gateways with JWT auth across 12 APIs.",
                    "Spearheaded SQL performance tuning, decreasing transaction time by 62%.",
                    "Implemented CI/CD with Jenkins and Docker for 10 microservices.",
                    "Mentored and interviewed 14 hires, improving ramp time by 35%.",
                    "Validated architectural improvements that reduced infrastructure costs by 28%.",
                ],
            ),
            ExperienceEntry(
                title="Junior PHP / Laravel Developer",
                company="adesso SE",
                dates="03/2013 – 05/2017",
                bullets=[
                    "Developed RESTful endpoints in Laravel and PHP for 8 customer-facing features.",
                    "Wrote SQL queries and optimized MySQL schemas, improving report times by 47%.",
                    "Integrated third-party APIs with retry logic, reducing failed calls by 55%.",
                    "Created PHPUnit unit tests, raising coverage across 10 modules.",
                    "Collaborated on HTML/CSS/JavaScript fixes, reducing client issues by 40%.",
                    "Configured CI pipelines with Git hooks, decreasing manual release steps by 70%.",
                    "Implemented role-based authorization to address OWASP findings.",
                    "Participated in Agile scrum ceremonies and code reviews for biweekly sprints.",
                ],
            ),
        ],
        education=[],
        certifications=[],
        languages=["English — C1"],
    )
    master = MasterCvData(
        contact=ContactInfo(name="Stefan Stepic"),
        is_structured=True,
        experience=[
            CvExperienceEntry(
                title="Tech Lead / Software Engineer",
                company="Future Processing",
                dates="07/2017 – 09/2021",
            ),
            CvExperienceEntry(
                title="Junior PHP / Laravel Developer",
                company="adesso SE",
                dates="03/2013 – 05/2017",
            ),
        ],
        skills_raw=[],
        certifications_raw=[],
        raw_text="",
    )
    report = validate_and_fix_resume(tailored, master, None, main_stack=".NET")
    assert any("main stack" in issue.lower() or "competing-stack" in issue.lower() for issue in report.issues)

    junior = tailored.experience[1]
    assert "php" not in junior.title.lower()
    assert "laravel" not in junior.title.lower()
    # Most competing-stack bullets rewritten; up to 2 may remain.
    competing = sum(
        1
        for b in junior.bullets
        if "php" in b.lower() or "laravel" in b.lower() or "phpunit" in b.lower()
    )
    assert competing <= 2
    assert competing < len(junior.bullets)


def test_validator_keeps_two_secondary_competing_bullets():
    """Up to 2 competing-stack bullets per job are allowed; the rest stay .NET."""
    bullets = [
        "Built ASP.NET Core APIs with EF Core for 12 endpoints.",
        "Optimized SQL Server queries, cutting report time by 40%.",
        "Added Redis caching for 8 high-traffic .NET services.",
        "Shipped Dockerized .NET services via Azure DevOps for 5 apps.",
        "Mentored 3 juniors on C# and SOLID practices over 6 months.",
        "Designed RabbitMQ consumers in .NET processing 50k messages/day.",
        # Allowed minority (competing primary stack / adjacent):
        "Maintained a small Laravel admin tool in PHP for 2 internal reports.",
        "Wrote PHPUnit smoke tests covering 4 legacy PHP endpoints.",
    ]
    tailored = TailoredResumeContent(
        contact=ContactInfo(name="Stefan Stepic"),
        summary="Backend engineer.",
        skills=SkillCategories(languages=["C#"]),
        experience=[
            ExperienceEntry(
                title="Software Engineer",
                company="Netguru",
                dates="11/2021 – 02/2023",
                bullets=bullets,
            )
        ],
        education=[],
        certifications=[],
        languages=["English — C1"],
    )
    master = MasterCvData(
        contact=ContactInfo(name="Stefan Stepic"),
        is_structured=True,
        experience=[CvExperienceEntry(title="Software Engineer", company="Netguru", dates="11/2021 – 02/2023")],
        skills_raw=[],
        certifications_raw=[],
        raw_text="",
    )
    validate_and_fix_resume(tailored, master, None, main_stack=".NET")
    competing = sum(
        1
        for b in tailored.experience[0].bullets
        if "php" in b.lower() or "laravel" in b.lower() or "phpunit" in b.lower()
    )
    assert competing == 2
    assert "Laravel" in tailored.experience[0].bullets[6] or "laravel" in tailored.experience[0].bullets[6].lower()
