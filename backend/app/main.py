"""FastAPI application entrypoint for the Resume Tailor AI backend."""
import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Playwright (see app/services/template_renderer.py) launches Chromium as a
# subprocess, which asyncio's default SelectorEventLoop on Windows cannot
# do (raises NotImplementedError). Must be set before uvicorn's event loop
# is created - this module-level statement runs at import time, which is
# early enough even under `uvicorn --reload`'s subprocess.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, auth, resume
from app.core.config import settings
from app.db.session import init_db
from app.models.schemas import HealthResponse
from app.services import docx_to_pdf, template_renderer
from app.services.ai_tailor import _get_client, _is_reasoning_model, reset_openai_client
from app.services.template_registry import seed_templates_from_disk

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
_FRONTEND_INDEX = _FRONTEND_DIST / "index.html"

# Ensure per-request performance reports (app/utils/timing.py) and this
# module's own startup banner are visible in the console regardless of
# uvicorn's own log configuration.
logging.getLogger("resume_tailor.perf").setLevel(logging.INFO)
logging.getLogger("resume_tailor.startup").setLevel(logging.INFO)
_startup_logger = logging.getLogger("resume_tailor.startup")


def _log_active_config() -> None:
    """Print the ACTUALLY active OpenAI/tailoring config on every boot.

    Exists because .env edits are a very common source of "I fixed it but
    it's still broken" confusion in this app: `uvicorn --reload`'s
    file-watcher only reacts to *.py changes by default, so an edited
    OPENAI_MODEL/timeout/tailoring_mode value in .env silently does NOT
    take effect until the server process is actually stopped and
    restarted - editing the file alone is not enough. Printing this on
    every boot makes that instantly verifiable instead of guessable: if
    the console doesn't show your edited value, the process wasn't
    actually restarted yet.
    """
    reasoning_note = " (REASONING MODEL - can take 8-230+s/call)" if _is_reasoning_model(settings.openai_model) else ""
    lines = [
        "========== ACTIVE CONFIG (from backend/.env) ==========",
        f"OPENAI_MODEL................... {settings.openai_model}{reasoning_note}",
        f"OPENAI_REQUEST_TIMEOUT_SECONDS.. {settings.openai_request_timeout_seconds}",
        f"OPENAI_CONNECT_TIMEOUT_SECONDS.. {settings.openai_connect_timeout_seconds}",
        f"OPENAI_MAX_RETRIES.............. {settings.openai_max_retries}",
        f"OPENAI_API_KEY set?............. {'yes' if settings.openai_api_key else 'NO - tailoring will fail'}",
        f"JWT_SECRET set?................. {'yes' if settings.jwt_secret.strip() else 'NO - sign-in will fail'}",
        f"GOOGLE_CLIENT_ID set?........... {'yes' if settings.google_client_id.strip() else 'no (email/password only)'}",
        f"TAILORING_MODE.................. {settings.tailoring_mode}",
        f"TAILORING_TIME_BUDGET_SECONDS... {settings.tailoring_time_budget_seconds}",
        "=========================================================",
    ]
    banner = "\n".join(lines)
    print(banner)
    _startup_logger.info(banner)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    reset_openai_client()
    _log_active_config()
    init_db()
    seed_templates_from_disk(_STATIC_DIR)
    await template_renderer.start_browser()
    yield
    # Cleanly quit the warm Word COM instance (see docx_to_pdf.py) and the
    # warm Playwright Chromium instance (see template_renderer.py) rather
    # than leaving orphaned processes on server shutdown.
    docx_to_pdf.shutdown()
    await template_renderer.stop_browser()
    reset_openai_client()


app = FastAPI(
    title="Resume Tailor AI API",
    description="Backend for generating job-tailored resumes from a master CV.",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins = settings.cors_origin_list
_allow_all_origins = _cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all_origins else _cors_origins,
    allow_credentials=not _allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Resume-Folder-Name", "X-Resume-File-Name", "Content-Disposition"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(resume.router)
# Serves generated template gallery thumbnails (see
# app/services/template_registry.py) at /static/template_previews/<slug>.png.
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", message="healthy")


@app.get("/health/openai")
async def health_openai() -> dict:
    """Cheap, fast (~1 API call, no tokens generated) connectivity + auth
    check against OpenAI, completely decoupled from the tailoring prompt/
    pipeline - exists specifically to bisect a "Request timed out" report:

    - If THIS also times out/fails: the problem is network/DNS/firewall/
      proxy reachability to api.openai.com, or an invalid/missing
      OPENAI_API_KEY - not anything about the tailoring prompt, CV size, or
      chosen model's reasoning behavior.
    - If THIS succeeds quickly but /api/resume/tailor still times out: the
      problem is specific to that request (e.g. OPENAI_MODEL is still a
      reasoning model, or the tailoring prompt/output is unusually large) -
      see the ACTIVE CONFIG banner printed on server startup and the error
      message from /api/resume/tailor itself, which now both report the
      exact active model/timeout.

    Uses the exact same client/timeout/retry configuration as tailoring
    (see app/services/ai_tailor._get_client), so the result is directly
    comparable.
    """
    if not settings.openai_api_key:
        return {"ok": False, "error": "OPENAI_API_KEY is not set in backend/.env."}

    client = _get_client()
    started = time.perf_counter()
    try:
        await client.models.retrieve(settings.openai_model)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "model": settings.openai_model,
            "error": str(exc),
        }
    return {
        "ok": True,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "model": settings.openai_model,
        "timeout_seconds": settings.openai_request_timeout_seconds,
        "reasoning_effort": settings.openai_reasoning_effort,
    }


# Serve the built React app from the same origin as the API so one public
# URL works (Cloudflare Tunnel, Render, Hugging Face). Registered last so
# it cannot shadow /api, /health, /static, or /docs.
if _FRONTEND_INDEX.is_file():
    _frontend_assets = _FRONTEND_DIST / "assets"
    if _frontend_assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_frontend_assets)), name="frontend-assets")

    @app.get("/")
    async def spa_index() -> FileResponse:
        return FileResponse(_FRONTEND_INDEX)

    @app.get("/{full_path:path}")
    async def spa_or_asset(full_path: str) -> FileResponse:
        target = (_FRONTEND_DIST / full_path).resolve()
        try:
            target.relative_to(_FRONTEND_DIST.resolve())
        except ValueError:
            return FileResponse(_FRONTEND_INDEX)
        if target.is_file():
            return FileResponse(target)
        return FileResponse(_FRONTEND_INDEX)
else:

    @app.get("/", response_model=HealthResponse)
    async def root() -> HealthResponse:
        return HealthResponse(status="ok", message="Resume Tailor AI API is running.")
