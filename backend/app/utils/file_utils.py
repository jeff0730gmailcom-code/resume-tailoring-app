"""Temporary file storage helpers.

Uploaded CVs and their AI-tailored content are written to a per-request
temp directory on disk, namespaced by a generated file id. Template
selection + resume history now live in the SQLite database (see
app/db/models.py) rather than on disk - see app/api/routes/resume.py.
"""
import json
import uuid
import zipfile
from pathlib import Path

from app.core.config import settings
from app.models.schemas import ApplicationAnswerItem, CoverLetterContent, MasterCvData, TailoredResumeContent
from app.services.employer_overrides import apply_candidate_employer_overrides

# DOCX / DOC / PDF.
ALLOWED_CV_EXTENSIONS = {".docx", ".doc", ".pdf"}

CV_TEXT_FILENAME = "cv_text.txt"
MASTER_CV_FILENAME = "master_cv.json"
TAILORED_RESUME_FILENAME = "tailored_resume.json"
COVER_LETTER_FILENAME = "cover_letter.json"
APPLICATION_ANSWERS_FILENAME = "application_answers.json"
TAILORED_PDF_FILENAME = "tailored_resume.pdf"
TAILORED_DOCX_FILENAME = "tailored_resume.docx"
PERF_STAGES_FILENAME = "perf_stages.json"
OWNER_FILENAME = "owner.json"


def generate_temp_file_id() -> str:
    """Generate a unique id to namespace a user's temporary files."""
    return uuid.uuid4().hex


def get_file_dir(file_id: str) -> Path:
    """Resolve (and create) the temp directory for a given file id."""
    file_dir = settings.temp_storage_path / file_id
    file_dir.mkdir(parents=True, exist_ok=True)
    return file_dir


def save_file_owner(file_id: str, user_id: int) -> None:
    path = get_file_dir(file_id) / OWNER_FILENAME
    path.write_text(json.dumps({"user_id": user_id}), encoding="utf-8")


def get_file_owner_id(file_id: str) -> int | None:
    path = get_file_dir(file_id) / OWNER_FILENAME
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    user_id = payload.get("user_id")
    return int(user_id) if user_id is not None else None


def save_upload(file_id: str, original_filename: str, content: bytes) -> Path:
    """Save the raw uploaded CV bytes to disk, preserving its extension."""
    suffix = Path(original_filename).suffix.lower()
    dest = get_file_dir(file_id) / f"original{suffix}"
    dest.write_bytes(content)
    return dest


def save_cv_text(file_id: str, text: str) -> None:
    (get_file_dir(file_id) / CV_TEXT_FILENAME).write_text(text, encoding="utf-8")


def load_cv_text(file_id: str) -> str | None:
    path = get_file_dir(file_id) / CV_TEXT_FILENAME
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_master_cv(file_id: str, master_cv: MasterCvData) -> None:
    """Persist the structured master-CV JSON (see app/services/
    cv_structurer.py) so /tailor always reads pre-parsed, cached data
    instead of re-parsing the CV or re-sending its raw text to the AI."""
    path = get_file_dir(file_id) / MASTER_CV_FILENAME
    path.write_text(master_cv.model_dump_json(indent=2), encoding="utf-8")


def load_master_cv(file_id: str) -> MasterCvData | None:
    path = get_file_dir(file_id) / MASTER_CV_FILENAME
    if not path.exists():
        return None
    master_cv = MasterCvData.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return apply_candidate_employer_overrides(master_cv)


def save_perf_stages(file_id: str, stages: dict[str, float]) -> None:
    """Persist accumulated performance-report stage durations for a
    file_id, so /tailor and /download's reports can include /upload's (and
    each other's) timings and print one cumulative pipeline report - see
    app/utils/timing.py."""
    path = get_file_dir(file_id) / PERF_STAGES_FILENAME
    path.write_text(json.dumps(stages), encoding="utf-8")


def load_perf_stages(file_id: str) -> dict[str, float]:
    path = get_file_dir(file_id) / PERF_STAGES_FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_original_cv_path(file_id: str) -> Path | None:
    """Resolve the originally-uploaded CV file for a given file id, if any."""
    for suffix in (".docx", ".pdf", ".doc"):
        candidate = get_file_dir(file_id) / f"original{suffix}"
        if candidate.exists():
            return candidate
    return None


def get_tailored_docx_path(file_id: str) -> Path:
    return get_file_dir(file_id) / TAILORED_DOCX_FILENAME


def save_tailored_resume(file_id: str, resume: TailoredResumeContent) -> None:
    path = get_file_dir(file_id) / TAILORED_RESUME_FILENAME
    path.write_text(resume.model_dump_json(indent=2), encoding="utf-8")


def load_tailored_resume(file_id: str) -> TailoredResumeContent | None:
    path = get_file_dir(file_id) / TAILORED_RESUME_FILENAME
    if not path.exists():
        return None
    return TailoredResumeContent.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_cover_letter(file_id: str, cover_letter: CoverLetterContent) -> None:
    path = get_file_dir(file_id) / COVER_LETTER_FILENAME
    path.write_text(cover_letter.model_dump_json(indent=2), encoding="utf-8")


def save_application_answers(file_id: str, answers: list[ApplicationAnswerItem]) -> None:
    path = get_file_dir(file_id) / APPLICATION_ANSWERS_FILENAME
    payload = [item.model_dump() for item in answers]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_tailored_pdf_path(file_id: str) -> Path:
    return get_file_dir(file_id) / TAILORED_PDF_FILENAME


def write_download_zip(file_id: str, folder_name: str, inner_filename: str, source: Path, format: str) -> Path:
    """Pack `source` as `{folder_name}/{inner_filename}` inside a zip.

    Zip download name is `{folder_name}.zip`. Opening it shows a folder
    named like the zip, with the CV (`inner_filename`) inside.
    """
    zip_path = get_file_dir(file_id) / f"download_{format}.zip"
    arcname = f"{folder_name}/{inner_filename}"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source, arcname=arcname)
    return zip_path
