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


def test_every_technology_family_is_dated_not_only_mcp():
    """Languages, frameworks, cloud, data, DevOps, and AI products all have dates."""
    from app.services.tech_timeline import TECH_RULES

    keys = {rule.key for rule in TECH_RULES}
    for name in (
        "python", "typescript", "golang", "react", "fastapi", "django",
        "docker", "kubernetes", "terraform", "github actions",
        "postgresql", "redis", "kafka", "aws", "azure", "gcp",
        "pytorch", "langchain", "pinecone", "chatgpt", "mcp",
    ):
        assert name in keys

    # A 2012 role can use Python and Postgres, not Docker, Kubernetes, React, or FastAPI.
    old = "Jun 2012 to Aug 2012"
    assert job_allows_tech(old, TECH_INTRODUCED["python"])
    assert job_allows_tech(old, TECH_INTRODUCED["postgresql"])
    for name in ("docker", "kubernetes", "terraform", "react", "fastapi", "langchain", "mcp"):
        assert not job_allows_tech(old, TECH_INTRODUCED[name])

    rules = forbidden_techs_for_job(old)
    bullet = (
        "Built Docker images and Kubernetes services with React, FastAPI, "
        "Terraform, LangChain, and MCP, cutting deploy time by 30%."
    )
    cleaned = neutralize_anachronistic_text(bullet, text_mentions_forbidden(bullet, rules))
    lowered = cleaned.lower()
    for banned in ("docker", "kubernetes", "react", "fastapi", "terraform", "langchain", "mcp"):
        assert banned not in lowered

    # "java" must not eat "javascript", and "react" must not eat "reactive".
    java_rules = [rule for rule in TECH_RULES if rule.key == "java"]
    react_rules = [rule for rule in TECH_RULES if rule.key == "react"]
    assert "javascript" in neutralize_anachronistic_text("Wrote JavaScript services.", java_rules).lower()
    assert not text_mentions_forbidden("Built reactive services.", react_rules)


def test_release_dates_block_tools_before_they_existed():
    assert not job_allows_tech("Jan 2018 to Jul 2020", TECH_INTRODUCED["langchain"])
    assert not job_allows_tech("Jun 2013 to Aug 2015", TECH_INTRODUCED["fastapi"])
    assert not job_allows_tech("Jun 2013 to Aug 2015", TECH_INTRODUCED["next.js"])
    assert job_allows_tech("Sep 2025 to Present", TECH_INTRODUCED["mcp"])
    assert job_allows_tech("Dec 2022 to Nov 2025", TECH_INTRODUCED["mcp"])
    assert not job_allows_tech("Jul 2020 to Nov 2022", TECH_INTRODUCED["gpt-4o"])
    early = forbidden_techs_for_job("Jan 2014 – Dec 2014")
    assert text_mentions_forbidden("Built reactive services.", early) == []
    assert text_mentions_forbidden("Shipped React Native screens and a Next.js portal.", early)
    # A 2023-2024 role may say GPT-4, and that pattern must not eat "gpt-4o"
    # when only the later model is too new... both are too new for 2014, so
    # check the regex directly: stripping gpt-4 leaves gpt-4o intact.
    from app.services.tech_timeline import TECH_RULES

    gpt4_rules = [rule for rule in TECH_RULES if "gpt-4" in rule.aliases and "gpt-4o" not in rule.aliases]
    assert "gpt-4o" in neutralize_anachronistic_text("Tuned gpt-4o prompts.", gpt4_rules).lower()
    assert "gpt-4" not in neutralize_anachronistic_text("Tuned gpt-4 prompts.", gpt4_rules).lower()


def test_summary_and_skills_drop_tools_no_job_overlaps():
    tailored = TailoredResumeContent(
        contact=ContactInfo(name="Marko Baranji"),
        summary="Backend engineer using LangChain, Pinecone, and MCP for document search.",
        skills=SkillCategories(ai=["LangChain", "MCP"], backend=["FastAPI", "Django"]),
        experience=[
            ExperienceEntry(
                title="Python Backend Engineer",
                company="Ingsoftware",
                dates="Jan 2018 to Jul 2020",
                bullets=["Built Django APIs for fintech clients, cutting response time by 30%."] * 8,
            )
        ],
        education=[],
        certifications=[],
        languages=[],
    )
    master = MasterCvData(
        contact=ContactInfo(name="Marko Baranji"),
        is_structured=True,
        experience=[
            CvExperienceEntry(
                title="Python Backend Engineer",
                company="Ingsoftware",
                dates="Jan 2018 to Jul 2020",
                bullets=[],
            )
        ],
        skills_raw=[],
        certifications_raw=[],
        raw_text="",
    )
    validate_and_fix_resume(tailored, master, None)
    blob = f"{tailored.summary} {' '.join(tailored.skills.ai)} {' '.join(tailored.skills.backend)}".lower()
    assert "langchain" not in blob
    assert "mcp" not in blob
    assert "pinecone" not in blob
    # FastAPI shipped Dec 2018, and this role ran through Jul 2020, so it overlaps.
    assert "fastapi" in blob
    assert "django" in blob


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
