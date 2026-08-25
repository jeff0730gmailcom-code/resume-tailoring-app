"""Performance timing + reporting for the resume-generation pipeline.

No external profiling dependency — just accumulates named stage durations
and prints a formatted report:

========== PERFORMANCE REPORT ==========

CV Parsing.............0.82s
JD Analysis............0.28s
...

TOTAL.................6.97s

==========================================

Since CV Parsing (Step 1) is a one-time operation at upload while JD
Analysis/Resume Matching/Prompt Build/OpenAI/Validation happen at /tailor
and DOCX/PDF Generation happen at /download, a single "resume generation"
spans three separate HTTP requests in this app's architecture. To still
print ONE cumulative report matching the format above, each stage's
duration is persisted to disk per file_id (see app/utils/file_utils.py's
save_perf_stages/load_perf_stages) and carried forward: /tailor's report
already includes /upload's CV Parsing time, and /download's report
includes everything measured so far — the full pipeline.

If a stage exceeds its expected target time (STAGE_TARGETS below), a short
diagnostic block is printed under the report: which function is slow, why,
how to optimize it, and the estimated time savings.

Stages are additive within a single PerfReport: calling `stage(name)` more
than once with the same name (e.g. multiple OpenAI calls inside a
refinement loop) sums into a single reported total for that name.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger("resume_tailor.perf")

# Canonical print order, mirroring the pipeline's steps 1-9.
STAGE_ORDER = [
    "CV Parsing",
    "JD Analysis",
    "Resume Matching",
    "Prompt Build",
    "OpenAI",
    "Validation",
    "Cover Letter",
    "Application Answers",
    "PDF Generation",
    "DOCX Generation",
    "Response",
]

# Upper bound of each step's target time.
STAGE_TARGETS: dict[str, float] = {
    "CV Parsing": 1.0,
    "JD Analysis": 0.5,
    "Resume Matching": 0.3,
    "Prompt Build": 0.2,
    "OpenAI": 60.0,
    "Validation": 0.3,
    "Cover Letter": 90.0,
    "Application Answers": 90.0,
    "PDF Generation": 1.0,
    "DOCX Generation": 1.5,
    "Response": 0.1,
}

# Static, per-stage guidance printed when a stage exceeds its target above.
# These describe *this codebase's* actual implementation of each stage, not
# generic advice, so they stay directly actionable.
STAGE_DIAGNOSTICS: dict[str, dict[str, str]] = {
    "CV Parsing": {
        "function": "cv_parser.extract_text_from_cv / cv_structurer.structure_cv",
        "reason": "A large DOCX/PDF, or a scanned/complex PDF that pypdf has to walk page by page.",
        "fix": "Cap structuring effort for very long documents; the DOCX Document object is already parsed once and shared across text/style/structure extraction, so this is almost purely file-size bound.",
        "savings": "~0.2-0.5s on typical resumes; more on multi-page scanned PDFs.",
    },
    "JD Analysis": {
        "function": "jd_analyzer.analyze_job_description",
        "reason": "Pure regex/string work over the pasted JD text - only gets slow if the JD is unusually long (multiple pages pasted in).",
        "fix": "Truncate JD analysis to the first ~3000 characters, which covers the requirements/responsibilities sections in nearly all real postings.",
        "savings": "~0.05-0.1s",
    },
    "Resume Matching": {
        "function": "resume_matcher.match_resume_to_jd",
        "reason": "In-memory set comparisons - only gets slow with an unusually large number of experience entries/bullets.",
        "fix": "Already O(jobs x jd_terms); no change needed for realistic resume sizes.",
        "savings": "~0.02-0.05s",
    },
    "Prompt Build": {
        "function": "resume_tailor_prompt.build_structured_user_message",
        "reason": "String concatenation/formatting - should never meaningfully exceed target; a slow reading here usually means it's being timed together with something else.",
        "fix": "Verify no I/O or JSON re-serialization is happening inside this stage.",
        "savings": "~0.05s",
    },
    "OpenAI": {
        "function": "ai_tailor.tailor_resume / _parse_completion",
        "reason": "With the default OPENAI_MODEL=gpt-4o-mini (non-reasoning), this stage is almost always network + generation time only (~1-4s/call). A slow reading here on the default model usually means: (a) OPENAI_MODEL was overridden to a reasoning model (gpt-5*, o1/o3/o4*) - these spend 8-230+ hidden reasoning seconds per call even at reasoning_effort=minimal, (b) a refinement pass paid full latency (aggressive_match_ats_max_refine_attempts > 0 - keep at 0 for the <5s target), or (c) the OpenAI SDK's own built-in retry/backoff (see openai_max_retries) kicked in after a transient timeout on one attempt - this stage's timer includes those retries.",
        "fix": "Confirm OPENAI_MODEL is gpt-4o-mini, AGGRESSIVE_MATCH_ATS_MAX_REFINE_ATTEMPTS=0, and OPENAI_MAX_OUTPUT_TOKENS~2000 in .env. openai_request_timeout_seconds and tailoring_time_budget_seconds (app/core/config.py) bound worst-case latency. Prefer structured DOCX uploads over PDF/raw-text fallback (smaller prompts + smaller output schema).",
        "savings": "~90-220s per call from switching off a reasoning model; ~1-4s per avoided refinement pass; ~0.5-1.5s from a tighter output-token cap on long multi-job resumes.",
    },
    "Validation": {
        "function": "resume_validator.validate_and_fix_resume",
        "reason": "Simple list/string comparisons - a slow reading here almost always means an unusually large number of experience entries.",
        "fix": "No change needed for realistic resume sizes.",
        "savings": "~0.02-0.05s",
    },
    "Cover Letter": {
        "function": "ai_cover_letter.generate_cover_letter",
        "reason": "A second OpenAI call after the tailored resume, only when the user asked for a cover letter. Same model/timeout as tailoring.",
        "fix": "Skip this stage by leaving include_cover_letter false. Confirm OPENAI_REASONING_EFFORT=minimal if using gpt-5-mini.",
        "savings": "The whole stage (~8-90s) if the cover letter is not needed.",
    },
    "Application Answers": {
        "function": "ai_application_answers.generate_application_answers",
        "reason": "A further OpenAI call after the tailored resume, only when the user added screening questions.",
        "fix": "Leave the questions list empty to skip this stage.",
        "savings": "The whole stage (~8-90s) if no application questions were added.",
    },
    "PDF Generation": {
        "function": "template_renderer.render_pdf",
        "reason": "A warm Playwright Chromium instance is kept alive across requests (see template_renderer.py's start_browser, called from app/main.py's lifespan) - this stage should only be slow on the very first request after server startup (browser cold start), not on steady-state requests.",
        "fix": "If this is consistently slow (not just the first request), check for antivirus/real-time-scan overhead on the Chromium process, or verify `playwright install chromium` was run so no on-demand download happens.",
        "savings": "~1-2s already recovered by reusing a warm browser instance instead of launching Chromium per request.",
    },
    "DOCX Generation": {
        "function": "docx_to_pdf.convert_to_docx",
        "reason": "Only runs when format=docx is requested - opens the just-rendered PDF via a fresh Word COM instance and SaveAs2 as .docx; PDF->DOCX conversion is inherently slower than a warm-instance DOCX->PDF export.",
        "fix": "Already scoped to only the docx download path (pdf downloads skip this stage entirely); further gains would require a non-Word PDF->DOCX converter.",
        "savings": "~0.5-1s from only paying this cost when the user actually requests a .docx download.",
    },
    "Response": {
        "function": "api/routes/resume.py (save + respond)",
        "reason": "Disk write of the tailored resume JSON - should never meaningfully exceed target.",
        "fix": "N/A at this size; would only matter with a much larger response payload.",
        "savings": "~0.01-0.02s",
    },
}


@dataclass
class PerfReport:
    label: str
    _stages: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Time the wrapped block and add its duration to `name`'s total."""
        started = time.perf_counter()
        try:
            yield
        finally:
            self.add(name, time.perf_counter() - started)

    def add(self, name: str, seconds: float) -> None:
        """Manually record a duration for `name` (for timings measured
        outside a `with perf.stage(...)` block, e.g. across an
        asyncio.to_thread call)."""
        self._stages[name] = self._stages.get(name, 0.0) + seconds

    def stage_seconds(self, name: str) -> float:
        return self._stages.get(name, 0.0)

    def seed(self, stages: dict[str, float]) -> None:
        """Pre-load stage durations measured in an earlier request (e.g.
        /tailor seeding /upload's CV Parsing time) so the report stays
        cumulative across the pipeline's separate HTTP calls."""
        for name, seconds in stages.items():
            self._stages.setdefault(name, seconds)

    def snapshot(self) -> dict[str, float]:
        """All stage durations recorded so far, for persisting to disk."""
        return dict(self._stages)

    def render(self) -> str:
        """Build the exact-format report string (see module docstring)."""
        pairs = [(name, self._stages[name]) for name in STAGE_ORDER if name in self._stages]
        total = sum(seconds for _, seconds in pairs)

        value_strs = {name: f"{seconds:.2f}s" for name, seconds in pairs}
        total_str = f"{total:.2f}s"
        width = max(
            [len(name) + len(value_strs[name]) for name in value_strs]
            + [len("TOTAL") + len(total_str)]
        ) + 12

        lines = ["========== PERFORMANCE REPORT ==========", ""]
        for name, seconds in pairs:
            value_str = value_strs[name]
            dots = "." * max(width - len(name) - len(value_str), 3)
            lines.append(f"{name}{dots}{value_str}")
        lines.append("")
        dots = "." * max(width - len("TOTAL") - len(total_str), 3)
        lines.append(f"TOTAL{dots}{total_str}")
        lines.append("")
        lines.append("=" * 42)

        for name, seconds in pairs:
            target = STAGE_TARGETS.get(name)
            if target is not None and seconds > target:
                lines.append("")
                lines.extend(_diagnostic_block(name, seconds, target))

        return "\n".join(lines)

    def log(self) -> None:
        """Print the timing report for this request to the console, and
        also emit it through the standard logger for anyone consuming logs
        programmatically."""
        report = self.render()
        print(report)
        logger.info("Performance report [%s]\n%s", self.label, report)


def _diagnostic_block(name: str, seconds: float, target: float) -> list[str]:
    info = STAGE_DIAGNOSTICS.get(name)
    if info is None:
        return [f"SLOW STEP: {name} took {seconds:.2f}s (target: {target:.1f}s)"]
    return [
        f"SLOW STEP: {name} took {seconds:.2f}s (target: <= {target:.1f}s)",
        f"  Function:  {info['function']}",
        f"  Why:       {info['reason']}",
        f"  Fix:       {info['fix']}",
        f"  Est. savings: {info['savings']}",
    ]
