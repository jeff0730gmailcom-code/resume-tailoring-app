"""Save tailored CVs into a real folder under the Windows user's Downloads.

This only runs when the API is on the user's own PC. Railway/Linux
containers must not write here — those files would stay on the server.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"


class DownloadsFolderError(Exception):
    """Raised when the user's Downloads folder cannot be found or written."""


def is_cloud_host() -> bool:
    """True when this process is a hosted container, not the user's PC."""
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"):
        return True
    if os.environ.get("RENDER") or os.environ.get("FLY_APP_NAME"):
        return True
    return False


def resolve_downloads_dir() -> Path | None:
    """Return the current Windows user's Downloads folder, if it exists."""
    if sys.platform != "win32":
        return None

    candidates: list[Path] = []
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, _DOWNLOADS_GUID)
            candidates.append(Path(value))
    except OSError:
        pass

    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidates.append(Path(userprofile) / "Downloads")
    candidates.append(Path.home() / "Downloads")

    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            return path
    return None


def can_save_to_user_downloads() -> bool:
    """Whether this process can create a folder in the user's real Downloads."""
    if is_cloud_host():
        return False
    return resolve_downloads_dir() is not None


def save_resume_to_downloads(folder_name: str, file_name: str, source: Path) -> Path:
    """Create `{Downloads}/{folder_name}/` and copy `source` in as `file_name`."""
    if not folder_name or not file_name:
        raise DownloadsFolderError("Missing folder or file name for the resume export.")
    if not source.is_file():
        raise DownloadsFolderError("The rendered resume file is missing.")

    downloads = resolve_downloads_dir()
    if downloads is None:
        raise DownloadsFolderError("Could not find your Downloads folder.")

    dest_dir = downloads / folder_name
    dest_file = dest_dir / file_name
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest_file)
    except OSError as exc:
        raise DownloadsFolderError(f"Could not save the resume to Downloads: {exc}") from exc
    return dest_file
