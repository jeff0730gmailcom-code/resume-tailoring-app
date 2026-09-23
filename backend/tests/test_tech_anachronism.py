"""Regression: never claim tools on jobs that ended before those tools existed."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

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
from app.services.tech_timeline import (  # noqa: E402
    TECH_INTRODUCED,
    forbidden_techs_for_job,
    job_allows_tech,
    neutralize_anachronistic_text,
    text_mentions_forbidden,
)


def test_mcp_not_allowed_before_nov_2024():
    intro = TECH_INTRODUCED["mcp"]
    assert intro == date(2024, 11, 1)
    assert not job_allows_tech("06/2013 – 08/2014", intro)
    assert not job_allows_tech("10/2014 – 05/2017", intro)
    assert not job_allows_tech("07/2020 – 08/2023", intro)
    assert job_allows_tech("09/2023 – 2/2026", intro)
    assert job_allows_tech("01/2025 – Present", intro)


def test_forbidden_techs_for_pre_mcp_job():
    rules = forbidden_techs_for_job("06/2013 – 08/2014")
    assert any("mcp" in r.aliases or r.key == "mcp" for r in rules)


def test_neutralize_mcp_phrases():
    rules = forbidden_techs_for_job("2017 – 2020")
    text = "Built MCP server governance and an MCP registry for 40 MCP artifacts."
    hits = text_mentions_forbidden(text, rules)
    assert hits
    cleaned = neutralize_anachronistic_text(text, hits)
    assert "mcp" not in cleaned.lower()
    assert "model context protocol" not in cleaned.lower()


def test_validator_strips_mcp_from_old_roles_keeps_recent():
    intern_bullets = [
        "Built simple Python scripts to populate a prototype MCP registry with 1,200 entries.",
        "Created Terraform examples for provisioning sandbox MCP servers used by 6 teams.",
        "Implemented basic approval simulations using SQS and Lambda for 4 workflows.",
        "Assisted senior engineers in testing migration scenarios for 10 dry-run migrations.",
        "Configured CloudWatch dashboards to surface onboarding job failures, cutting retry time by 30%.",
        "Helped automate metadata validation rules in Python, blocking 150 invalid records.",
        "Contributed to CI job templates in GitLab CI for 20 PRs.",
        "Prepared onboarding guides explaining MCP concepts to cross-functional teams.",
    ]
    recent_bullets = [
        "Designed MCP server governance workflows using Python ETL and AWS Lambda across 120 servers.",
        "Built registry lifecycle management in Terraform and DynamoDB for 200+ MCP artifacts.",
        "Implemented approval gates with AWS Step Functions and IAM policies, raising compliant approvals by 35%.",
        "Led migrations of 60 MCP servers into the enterprise registry using SSM Run Command.",
        "Developed Grafana and CloudWatch dashboards, improving SLA adherence by 22%.",
        "Authored onboarding pipelines integrating ServiceNow and Okta, cutting manual steps by 70%.",
        "Managed cost and security controls via AWS Config and Terraform, reducing non-compliant resources by 40%.",
        "Mentored 12 engineers on MCP concepts, Python scripting, and governance patterns.",
    ]
    tailored = TailoredResumeContent(
        contact=ContactInfo(name="Mateo Baranji"),
        summary="Platform engineer with MCP experience.",
        skills=SkillCategories(tools=["MCP"]),
        experience=[
            ExperienceEntry(
                title="Intern",
                company="Scott Logic",
                dates="06/2013 – 08/2014",
                bullets=list(intern_bullets),
            ),
            ExperienceEntry(
                title="Senior AWS Infrastructure Engineer",
                company="Talon.One",
                dates="09/2023 – 2/2026",
                bullets=list(recent_bullets),
            ),
        ],
        education=[],
        certifications=[],
        languages=["English — C1"],
    )
    master = MasterCvData(
        contact=ContactInfo(name="Mateo Baranji"),
        is_structured=True,
        experience=[
            CvExperienceEntry(
                title="Intern",
                company="Scott Logic",
                dates="06/2013 – 08/2014",
                bullets=[],
            ),
            CvExperienceEntry(
                title="Senior AWS Infrastructure Engineer",
                company="Talon.One",
                dates="09/2023 – 2/2026",
                bullets=[],
            ),
        ],
        skills_raw=[],
        certifications_raw=[],
        raw_text="",
    )
    report = validate_and_fix_resume(tailored, master, None)
    assert any("anachronistic" in issue.lower() for issue in report.issues)

    intern = tailored.experience[0]
    for bullet in intern.bullets:
        assert "mcp" not in bullet.lower()
        assert "model context protocol" not in bullet.lower()

    recent = " ".join(tailored.experience[1].bullets).lower()
    assert "mcp" in recent
