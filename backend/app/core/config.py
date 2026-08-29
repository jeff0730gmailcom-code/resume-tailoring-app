"""Application configuration loaded from environment variables."""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from this file's location (backend/.env) so uvicorn --reload
# worker processes always load the same file regardless of process cwd.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = ""
    # Default model is gpt-5-mini (reasoning family). Keep
    # openai_reasoning_effort=minimal and openai_request_timeout_seconds
    # high enough (120s) — 30s timeouts were the main cause of
    # "Request timed out." with this model. See ai_tailor._parse_completion.
    openai_model: str = "gpt-5-mini"
    # Reasoning effort for gpt-5* / o-series. "minimal" is the fastest
    # supported setting for gpt-5-mini (it does not accept "none").
    openai_reasoning_effort: str = "minimal"
    # Per-attempt timeout. gpt-5-mini needs well above 30s even at minimal
    # effort on structured resume calls.
    openai_request_timeout_seconds: float = 120.0
    openai_connect_timeout_seconds: float = 10.0
    # 1 retry for transient blips; keep low so failures don't multiply.
    openai_max_retries: int = 1
    # Shared budget for hidden reasoning tokens + visible JSON. Too low
    # (e.g. 1000) can exhaust the budget on reasoning and return empty
    # structured output for gpt-5-mini — 4000 is the safe default here.
    openai_max_output_tokens: int = 6000
    # Soft deadline for starting refinement passes only (first call always
    # runs). Raised for gpt-5-mini headroom.
    tailoring_time_budget_seconds: float = 90.0

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Temporary storage
    temp_storage_dir: str = "temp"

    # SQLite database - resume templates + resume-generation history (see
    # app/db/models.py). A single file, created automatically on startup
    # (app/db/session.init_db()) - no separate DB server to run.
    database_dir: str = "data"
    database_filename: str = "app.db"

    # Upload limits
    max_upload_size_mb: int = 10

    # ATS keyword-match tuning. Defaults to 0 refinement passes so a tailor
    # request makes EXACTLY ONE OpenAI call, no exceptions - each refinement
    # pass is a full extra sequential OpenAI round trip (unavoidable: it
    # depends on the previous pass's output), so with a slow model/effort
    # setting this is what turns a 100s single call into a 300s+ request.
    # Set > 0 only as an opt-in safety net if you want a second pass to
    # chase a low first-pass ATS score at the cost of ~1x more latency.
    ats_score_target: float = 0.95
    ats_max_refine_attempts: int = 0

    # Tailoring mode (see app/prompts/resume_tailor_prompt.py and
    # app/services/resume_matcher.py for how each mode behaves):
    # - "accurate": only ever states information explicitly supported (incl.
    #   transferably) by the master CV. Never claims hands-on experience with
    #   a tool/technology the CV gives no genuine basis for.
    # - "aggressive": same truthfulness floor, but tries harder to get there -
    #   broader transferable-skill discovery, more assertive rewriting
    #   (rewrite bullets rather than append keywords), stronger
    #   prioritization/reordering toward the JD, and a bigger refinement
    #   budget. It does NOT fabricate experience with technologies that have
    #   no genuine transferable basis anywhere in the CV - a JD skill with
    #   zero real connection to the candidate's background is still left out
    #   in both modes.
    # - "aggressive_match" (AGGRESSIVE_MATCH_MODE): the strongest intensity -
    #   full-resume rewrite permission, the widest transferable-skill search
    #   (app/services/resume_matcher.py's _MATCH_MODE_SKILL_FAMILIES), and a
    #   deterministic (non-AI) post-generation pass that tops up the Skills
    #   section with any matched/transferable skill the AI call still
    #   omitted (app/services/resume_validator.py's close_ats_gaps). An
    #   optional internal "improve and repeat" refine loop exists
    #   (aggressive_match_ats_max_refine_attempts) but defaults to 0 so the
    #   request stays on a single OpenAI call for the <5s target. Still the
    #   same hard truthfulness floor as the other two modes: a skill with
    #   zero transferable basis anywhere in the CV is still left out, never
    #   fabricated.
    tailoring_mode: Literal["accurate", "aggressive", "aggressive_match"] = "accurate"
    # Refinement-pass budget used only when tailoring_mode == "aggressive".
    # Defaults to 0 (exactly one OpenAI call) - "aggressive" gets its extra
    # ATS effort entirely from the single call (broader transferable-skill
    # hints + a more assertive prompt, see resume_matcher.py /
    # resume_tailor_prompt.py), not from extra sequential calls. Raise only
    # as an opt-in trade of latency for a second attempt.
    aggressive_ats_max_refine_attempts: int = 0
    # Same, for tailoring_mode == "aggressive_match". Defaults to 0 so a
    # tailor request makes EXACTLY ONE OpenAI call - required for the <5s
    # target. Each pass above 0 is a full extra sequential OpenAI round
    # trip (~1-4s with gpt-4o-mini) and is the single biggest latency
    # lever. ATS gaps after the single call are still closed for free by
    # close_ats_gaps (Skills top-up, no AI). Raise to 1 only if you need to
    # trade latency for a higher hit rate on unusually large skill gaps.
    aggressive_match_ats_max_refine_attempts: int = 0

    jwt_secret: str = ""
    jwt_expire_minutes: int = 60 * 24 * 7
    google_client_id: str = ""
    google_client_secret: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def temp_storage_path(self) -> Path:
        path = Path(self.temp_storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def database_path(self) -> Path:
        path = _BACKEND_DIR / self.database_dir
        path.mkdir(parents=True, exist_ok=True)
        return path / self.database_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"


settings = Settings()
