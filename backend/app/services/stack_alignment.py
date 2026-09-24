"""Main-stack alignment for tailored resumes.

Every experience bullet (and stack tokens embedded in job titles) must stay
inside the application's main technology family (e.g. .NET). Competing
stacks (PHP junior → .NET tech lead) are illogical and get rewritten.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StackFamily:
    key: str
    # Tokens that identify this family in free text / main_stack field.
    markers: tuple[str, ...]
    # Prefer longer phrases first when substituting.
    replacements_from_others: tuple[tuple[str, str], ...] = ()


# Family definitions. Markers are matched case-insensitively as whole tokens
# (or as known multi-word phrases).
STACK_FAMILIES: list[StackFamily] = [
    StackFamily(
        key="dotnet",
        markers=(".net", "dotnet", "c#", "csharp", "asp.net", "aspnet", "f#"),
    ),
    StackFamily(
        key="php",
        markers=("php", "laravel", "symfony", "wordpress", "magento", "phpunit"),
    ),
    StackFamily(
        key="java",
        markers=("java", "spring", "spring boot", "kotlin", "hibernate", "maven", "gradle"),
    ),
    StackFamily(
        key="nodejs",
        markers=("node.js", "nodejs", "node", "express", "nestjs", "typescript backend"),
    ),
    StackFamily(
        key="python",
        markers=("python", "django", "flask", "fastapi", "pytest"),
    ),
    StackFamily(
        key="golang",
        markers=("golang", "go lang"),
    ),
    StackFamily(
        key="ruby",
        markers=("ruby", "rails", "ror"),
    ),
    StackFamily(
        key="scala",
        markers=("scala", "akka", "play framework"),
    ),
    StackFamily(
        key="rust",
        markers=("rust", "actix", "axum"),
    ),
]

# Competing-stack → main-stack phrase swaps (applied only when rewriting
# away from a competing family toward the primary family).
_REWRITE_TO_DOTNET: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bPHPUnit\b"), "xUnit"),
    (re.compile(r"(?i)\bLaravel\b"), "ASP.NET Core"),
    (re.compile(r"(?i)\bSymfony\b"), "ASP.NET Core"),
    (re.compile(r"(?i)\bWordPress\b"), ".NET CMS integrations"),
    (re.compile(r"(?i)\bMagento\b"), ".NET e-commerce services"),
    (re.compile(r"(?i)\bPHP\b"), "C#/.NET"),
]

_REWRITE_TO_JAVA: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bPHPUnit\b"), "JUnit"),
    (re.compile(r"(?i)\bLaravel\b"), "Spring Boot"),
    (re.compile(r"(?i)\bSymfony\b"), "Spring Boot"),
    (re.compile(r"(?i)\bPHP\b"), "Java"),
    (re.compile(r"(?i)\bC#|\.NET\b|ASP\.NET(?: Core)?\b"), "Java/Spring"),
]

_REWRITE_TO_NODE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bPHPUnit\b"), "Jest"),
    (re.compile(r"(?i)\bLaravel\b"), "NestJS"),
    (re.compile(r"(?i)\bPHP\b"), "Node.js"),
    (re.compile(r"(?i)\bC#|\.NET\b|ASP\.NET(?: Core)?\b"), "Node.js"),
]

_REWRITE_TO_PYTHON: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bPHPUnit\b"), "pytest"),
    (re.compile(r"(?i)\bLaravel\b"), "Django"),
    (re.compile(r"(?i)\bPHP\b"), "Python"),
    (re.compile(r"(?i)\bC#|\.NET\b|ASP\.NET(?: Core)?\b"), "Python"),
]

_REWRITE_MAP: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "dotnet": _REWRITE_TO_DOTNET,
    "java": _REWRITE_TO_JAVA,
    "nodejs": _REWRITE_TO_NODE,
    "python": _REWRITE_TO_PYTHON,
}

# Max bullets per job that may mention a competing primary stack family
# (e.g. PHP on a .NET application). The rest must stay on main stack;
# secondary JD skills outside competing families are never rewritten.
MAX_COMPETING_STACK_BULLETS_PER_JOB = 2


def competing_bullet_indexes(bullets: list[str], primary: StackFamily) -> list[int]:
    """Indexes of bullets that mention a rival primary stack family."""
    return [i for i, bullet in enumerate(bullets) if competing_families_in_text(bullet, primary)]


def _normalize(text: str) -> str:
    raw = (text or "").lower()
    raw = raw.replace("c#", "csharp").replace("f#", "fsharp").replace("#", " ")
    return " ".join(raw.split())


def resolve_stack_family(main_stack: str) -> StackFamily | None:
    """Map a free-text main_stack (e.g. '.NET', 'dotnet', 'C#') to a family."""
    hay = _normalize(main_stack)
    if not hay:
        return None
    # Prefer longer/more specific markers.
    best: tuple[int, StackFamily] | None = None
    for family in STACK_FAMILIES:
        for marker in family.markers:
            m = marker.lower()
            if m in hay or m.replace(".", "") in hay.replace(".", ""):
                score = len(m)
                if best is None or score > best[0]:
                    best = (score, family)
    return best[1] if best else None


def _token_present(marker: str, text: str) -> bool:
    if " " in marker or "." in marker:
        return re.search(re.escape(marker), text, flags=re.IGNORECASE) is not None
    # Avoid matching "go" inside "ongoing" / "good".
    if marker.lower() in {"go", "node"}:
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(marker)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE) is not None
    if marker.lower() in {"c#", "f#"}:
        return re.search(re.escape(marker), text, flags=re.IGNORECASE) is not None
    if marker.lower() == ".net":
        return re.search(r"(?i)(?<![A-Za-z])\.NET\b|dotnet\b", text) is not None
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(marker)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE) is not None


def competing_families_in_text(text: str, primary: StackFamily) -> list[StackFamily]:
    hits: list[StackFamily] = []
    for family in STACK_FAMILIES:
        if family.key == primary.key:
            continue
        if any(_token_present(marker, text) for marker in family.markers):
            hits.append(family)
    return hits


def rewrite_toward_stack(text: str, primary: StackFamily) -> str:
    """Replace competing-stack tokens with main-stack equivalents."""
    updated = text
    for pattern, repl in _REWRITE_MAP.get(primary.key, []):
        updated = pattern.sub(repl, updated)
    # Generic fallback: drop remaining competing markers.
    for family in STACK_FAMILIES:
        if family.key == primary.key:
            continue
        for marker in sorted(family.markers, key=len, reverse=True):
            if " " in marker or "." in marker:
                updated = re.sub(re.escape(marker), primary.markers[0], updated, flags=re.IGNORECASE)
            elif marker.lower() in {"c#", "f#"}:
                updated = re.sub(re.escape(marker), primary.markers[0], updated, flags=re.IGNORECASE)
            else:
                updated = re.sub(
                    rf"(?<![A-Za-z0-9]){re.escape(marker)}(?![A-Za-z0-9])",
                    primary.markers[0],
                    updated,
                    flags=re.IGNORECASE,
                )
    updated = re.sub(r"\s{2,}", " ", updated)
    updated = re.sub(r"\s+([,/;|])", r"\1", updated)
    return updated.strip(" -–—/|,;")


def sanitize_title_for_stack(title: str, primary: StackFamily) -> str:
    """Remove competing-stack tokens from a preserved job title.

    Keeps seniority/role words (Junior, Tech Lead, Developer) so identity is
    recognizable, but drops embedded rival stacks (e.g. 'Junior PHP / Laravel
    Developer' → 'Junior Developer' for a .NET application).
    """
    updated = title or ""
    for family in STACK_FAMILIES:
        if family.key == primary.key:
            continue
        for marker in sorted(family.markers, key=len, reverse=True):
            updated = re.sub(
                rf"(?i)(?<![A-Za-z0-9]){re.escape(marker)}(?![A-Za-z0-9])",
                " ",
                updated,
            )
    updated = re.sub(r"\s*[|/]\s*[|/]\s*", " / ", updated)
    updated = re.sub(r"\s{2,}", " ", updated)
    updated = re.sub(r"\s*/\s*$", "", updated)
    updated = re.sub(r"^\s*/\s*", "", updated)
    updated = updated.strip(" -–—/|,")
    return updated or title


def prompt_stack_rules_block(main_stack: str) -> str:
    family = resolve_stack_family(main_stack)
    stack_label = (main_stack or "").strip() or "the JD primary stack"
    family_note = f" (family: {family.key})" if family else ""
    return (
        f"MAIN STACK (SOFT-HARD RULE): {stack_label}{family_note}. "
        f"MOST bullets in EVERY job must use this stack and its ecosystem "
        f"(about 6 of 8). Up to 1-2 bullets per job may focus on other skills "
        f"explicitly mentioned in the JD (e.g. React, Docker, Kafka, cloud) — "
        f"not a different primary career track. Do NOT turn an early role into "
        f"a different-language job (e.g. all-PHP junior then .NET Tech Lead). "
        f"Keep one primary stack story with seniority progression; sprinkle "
        f"secondary JD skills lightly."
    )
