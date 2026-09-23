"""Technology introduction dates for resume anachronism checks.

A tool may appear in a job's bullets only if that job's employment period
still overlaps the tool's public introduction (job end date on/after the
intro month). Pre-dating tools (e.g. MCP on a 2017 role) is a hard error
and is stripped deterministically after generation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.services.career_tenure import parse_job_date_range

# Public introduction month (first of month). Conservative: prefer slightly
# later than the absolute first commit/announcement when unclear.
TECH_INTRODUCED: dict[str, date] = {
    # Anthropic announced Model Context Protocol on 2024-11-25.
    "mcp": date(2024, 11, 1),
    "model context protocol": date(2024, 11, 1),
    # Other AI-era terms that commonly get backdated onto old roles:
    "chatgpt": date(2022, 11, 1),
    "gpt-4": date(2023, 3, 1),
    "gpt4": date(2023, 3, 1),
    "claude": date(2023, 3, 1),
    "langchain": date(2022, 10, 1),
    "llamaindex": date(2022, 11, 1),
    "openai api": date(2020, 6, 1),
    "github copilot": date(2021, 6, 1),
}


@dataclass(frozen=True)
class TechRule:
    key: str
    introduced: date
    # Longer aliases first so "model context protocol" wins over bare fragments.
    aliases: tuple[str, ...]


def _build_rules() -> list[TechRule]:
    by_intro: dict[date, list[str]] = {}
    for name, intro in TECH_INTRODUCED.items():
        by_intro.setdefault(intro, []).append(name)
    rules: list[TechRule] = []
    for intro, names in by_intro.items():
        # Canonical key = shortest acronym-like name when present.
        key = min(names, key=lambda n: (0 if len(n) <= 4 else 1, len(n)))
        aliases = tuple(sorted(set(names), key=len, reverse=True))
        rules.append(TechRule(key=key, introduced=intro, aliases=aliases))
    return rules


TECH_RULES: list[TechRule] = _build_rules()

# Neutral replacements when stripping anachronistic MCP wording from bullets.
_MCP_PHRASE_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bMCP[- ]compliant\b"), "enterprise"),
    (re.compile(r"(?i)\bMCP servers?\b"), "platform services"),
    (re.compile(r"(?i)\bMCP artifacts?\b"), "platform artifacts"),
    (re.compile(r"(?i)\bMCP (?:server )?governance\b"), "platform governance"),
    (re.compile(r"(?i)\bMCP registry\b"), "enterprise registry"),
    (re.compile(r"(?i)\bMCP (?:metadata|entries|deployments|concepts|onboarding|integrations?)\b"), "platform tooling"),
    (re.compile(r"(?i)\bModel Context Protocol\b"), "platform integration standards"),
    (re.compile(r"(?i)\bMCP\b"), "platform tooling"),
]

_OTHER_PHRASE_SUBS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "chatgpt": [(re.compile(r"(?i)\bChatGPT\b"), "AI assistants")],
    "gpt-4": [(re.compile(r"(?i)\bGPT-4\b"), "large language models")],
    "gpt4": [(re.compile(r"(?i)\bGPT-?4\b"), "large language models")],
    "claude": [(re.compile(r"(?i)\bClaude\b"), "AI assistants")],
    "langchain": [(re.compile(r"(?i)\bLangChain\b"), "AI orchestration tooling")],
    "llamaindex": [(re.compile(r"(?i)\bLlamaIndex\b"), "AI retrieval tooling")],
    "openai api": [(re.compile(r"(?i)\bOpenAI API\b"), "ML APIs")],
    "github copilot": [(re.compile(r"(?i)\bGitHub Copilot\b"), "developer tooling")],
}


def job_allows_tech(job_dates: str, introduced: date) -> bool:
    """True if the job period could overlap the technology's existence."""
    parsed = parse_job_date_range(job_dates)
    if parsed is None:
        # Unknown dates: do not strip (avoid false positives), but prompts
        # still instruct the model to respect eras.
        return True
    _start, end = parsed
    # Compare by month: end month on/after intro month is allowed.
    return date(end.year, end.month, 1) >= date(introduced.year, introduced.month, 1)


def forbidden_techs_for_job(job_dates: str) -> list[TechRule]:
    return [rule for rule in TECH_RULES if not job_allows_tech(job_dates, rule.introduced)]


def _alias_present(text: str, alias: str) -> bool:
    if " " in alias or "-" in alias:
        return re.search(re.escape(alias), text, flags=re.IGNORECASE) is not None
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE) is not None


def text_mentions_forbidden(text: str, rules: list[TechRule]) -> list[TechRule]:
    hits: list[TechRule] = []
    for rule in rules:
        if any(_alias_present(text, alias) for alias in rule.aliases):
            hits.append(rule)
    return hits


def neutralize_anachronistic_text(text: str, rules: list[TechRule]) -> str:
    """Replace forbidden tech mentions with era-neutral wording."""
    updated = text
    for rule in rules:
        if rule.key in {"mcp", "model context protocol"} or any(
            a in {"mcp", "model context protocol"} for a in rule.aliases
        ):
            for pattern, repl in _MCP_PHRASE_SUBS:
                updated = pattern.sub(repl, updated)
            continue
        for alias_key in rule.aliases:
            for pattern, repl in _OTHER_PHRASE_SUBS.get(alias_key, []):
                updated = pattern.sub(repl, updated)
        # Fallback: drop bare remaining aliases.
        for alias in rule.aliases:
            if " " in alias:
                updated = re.sub(re.escape(alias), "platform tooling", updated, flags=re.IGNORECASE)
            else:
                updated = re.sub(
                    rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
                    "platform tooling",
                    updated,
                    flags=re.IGNORECASE,
                )
    updated = re.sub(r"\s{2,}", " ", updated)
    updated = re.sub(r"\s+([,.;:])", r"\1", updated)
    return updated.strip(" -–,;")


def prompt_era_rules_block() -> str:
    """Compact TECH ERA rules injected into tailor prompts."""
    lines = [
        "TECH ERA (HARD RULE): never put a technology in a job's bullets if that "
        "job ended before the technology publicly existed. Put recent tools only "
        "on overlapping / later roles. Skills/summary may name current JD tools "
        "without backdating them onto old jobs.",
        "Known introduction months (non-exhaustive):",
    ]
    # Stable, readable order.
    seen: set[str] = set()
    for rule in sorted(TECH_RULES, key=lambda r: r.introduced):
        label = rule.aliases[0] if rule.aliases else rule.key
        if label in seen:
            continue
        seen.add(label)
        lines.append(f"- {label}: {rule.introduced.strftime('%Y-%m')} (not earlier)")
    lines.append(
        "Example: MCP (Model Context Protocol) launched 2024-11 — never claim MCP "
        "work in 2013–2023 roles; use API integrations, registries, cloud "
        "infrastructure, lifecycle management, or platform governance instead."
    )
    return "\n".join(lines)
