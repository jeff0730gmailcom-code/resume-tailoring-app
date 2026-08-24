"""Word COM helpers: DOCX<->PDF and PDF/DOC->DOCX.

convert_to_docx is used by app/api/routes/resume.py's /download endpoint to
derive an editable .docx from the resume PDF just rendered by
app/services/template_renderer.py (Jinja2 + Playwright). Requires Microsoft
Word to be installed.

Keeps ONE warm Word.Application for fast DOCX→PDF export. PDF/DOC→DOCX
conversion always uses a fresh Word instance (PDF open is dialog-prone and
was hanging the warm instance). Source files are copied to a space-free
temp directory before Open() — Word COM frequently hangs or fails on paths
containing spaces (this project's folder is under "New folder").
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_WD_FORMAT_PDF = 17
_WD_FORMAT_XML_DOCUMENT = 16  # .docx
_WD_ALERTS_NONE = 0

# DOCX→PDF is usually fast on a warm instance; PDF→DOCX needs more headroom.
_DOCX_TO_PDF_TIMEOUT_SECONDS = 45.0
_TO_DOCX_TIMEOUT_SECONDS = 90.0

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="word-com")
_word_app: Any = None
_com_initialized = False


def _ensure_word() -> Any | None:
    """Warm Word.Application for DOCX→PDF. Must run on _executor's thread."""
    global _word_app, _com_initialized
    if _word_app is not None:
        return _word_app

    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None

    if not _com_initialized:
        pythoncom.CoInitialize()
        _com_initialized = True

    try:
        app = win32com.client.DispatchEx("Word.Application")
        _configure_word_app(app)
        _word_app = app
    except Exception:  # noqa: BLE001
        _word_app = None
    return _word_app


def _configure_word_app(app: Any) -> None:
    """Suppress UI so Open/Save never blocks on modal dialogs."""
    app.Visible = False
    try:
        app.DisplayAlerts = _WD_ALERTS_NONE
    except Exception:  # noqa: BLE001
        pass
    try:
        app.ScreenUpdating = False
    except Exception:  # noqa: BLE001
        pass
    try:
        # msoAutomationSecurityForceDisable = 3
        app.AutomationSecurity = 3
    except Exception:  # noqa: BLE001
        pass


def _reset_word() -> None:
    global _word_app
    try:
        if _word_app is not None:
            _word_app.Quit()
    except Exception:  # noqa: BLE001
        pass
    _word_app = None


def _space_free_workdir() -> Path:
    """Word COM is unreliable with spaces in paths (e.g. '.../New folder/...')."""
    root = Path(tempfile.gettempdir()) / "resume_tailor_word"
    root.mkdir(parents=True, exist_ok=True)
    work = root / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    return work


def _open_document(word: Any, path: Path) -> Any:
    return word.Documents.Open(
        str(path.resolve()),
        ConfirmConversions=False,
        ReadOnly=True,
        AddToRecentFiles=False,
        Format=0,  # wdOpenFormatAuto
        Visible=False,
        OpenAndRepair=True,
        NoEncodingDialog=True,
    )


def _convert_to_docx_sync(source_path: Path, docx_path: Path) -> bool:
    """Fresh Word instance: open PDF/.doc and SaveAs .docx.

    Uses a space-free working copy of the source so Word does not hang on
    paths like '.../New folder/...'.
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return False

    pythoncom.CoInitialize()
    word = None
    document = None
    work = _space_free_workdir()
    try:
        safe_source = work / f"source{source_path.suffix.lower()}"
        shutil.copy2(source_path, safe_source)
        safe_out = work / "converted.docx"

        word = win32com.client.DispatchEx("Word.Application")
        _configure_word_app(word)
        document = _open_document(word, safe_source)
        document.SaveAs2(str(safe_out.resolve()), FileFormat=_WD_FORMAT_XML_DOCUMENT)
        document.Close(False)
        document = None

        docx_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_out, docx_path)
        return docx_path.exists() and docx_path.stat().st_size > 0
    except Exception:  # noqa: BLE001
        logger.warning(
            "Word COM convert-to-docx failed for %s",
            source_path,
            exc_info=True,
        )
        return False
    finally:
        try:
            if document is not None:
                document.Close(False)
        except Exception:  # noqa: BLE001
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:  # noqa: BLE001
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(work, ignore_errors=True)


async def convert_to_docx(source_path: Path, docx_path: Path) -> bool:
    """Convert PDF / .doc / .docx to an editable .docx via Word COM."""
    if source_path.suffix.lower() == ".docx":
        if source_path.resolve() == docx_path.resolve():
            return True
        try:
            docx_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, docx_path)
            return True
        except Exception:  # noqa: BLE001
            logger.warning("Failed to copy DOCX template %s -> %s", source_path, docx_path, exc_info=True)
            return False

    # Run on the dedicated COM executor so we never share apartments oddly,
    # but each call still spins a fresh Word (see _convert_to_docx_sync).
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_executor, _convert_to_docx_sync, source_path, docx_path)
    try:
        return await asyncio.wait_for(future, timeout=_TO_DOCX_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error(
            "Word COM convert-to-docx timed out after %.0fs for %s",
            _TO_DOCX_TIMEOUT_SECONDS,
            source_path,
        )
        _recover_from_hang()
        return False


def _convert_sync(docx_path: Path, pdf_path: Path) -> bool:
    """Warm-instance DOCX→PDF. Copies through a space-free path first."""
    word = _ensure_word()
    if word is None:
        return False

    work = _space_free_workdir()
    document = None
    try:
        safe_docx = work / "input.docx"
        safe_pdf = work / "output.pdf"
        shutil.copy2(docx_path, safe_docx)

        document = _open_document(word, safe_docx)
        document.SaveAs(str(safe_pdf.resolve()), FileFormat=_WD_FORMAT_PDF)
        document.Close(False)
        document = None

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_pdf, pdf_path)
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception:  # noqa: BLE001
        logger.warning("Word COM DOCX→PDF failed for %s - resetting warm instance", docx_path, exc_info=True)
        _reset_word()
        return False
    finally:
        try:
            if document is not None:
                document.Close(False)
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(work, ignore_errors=True)


def _recover_from_hang() -> None:
    """Abandon a stuck COM worker thread and drop the warm Word reference."""
    global _executor, _word_app
    logger.error("Word COM worker timed out - starting a fresh executor")
    _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="word-com")
    _word_app = None


async def convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> bool:
    """Convert docx_path to pdf_path using the warm Word instance."""
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_executor, _convert_sync, docx_path, pdf_path)
    try:
        return await asyncio.wait_for(future, timeout=_DOCX_TO_PDF_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        _recover_from_hang()
        return False


def shutdown() -> None:
    """Quit the warm Word instance on app shutdown."""
    try:
        _executor.submit(_reset_word).result(timeout=10)
    except Exception:  # noqa: BLE001
        pass
    _executor.shutdown(wait=False)
