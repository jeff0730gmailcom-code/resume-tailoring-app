"""Save tailored CVs into a real folder under the user's Downloads directory.

Browsers cannot create folders via Content-Disposition, so this local app
writes directly to Downloads instead of returning a zip.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows Known Folder GUID for Downloads (Shell Folders registry value).
_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"


class DownloadsFolderError(Exception):
    """Raised when the user's Downloads folder cannot be found or written."""


def resolve_downloads_dir() -> Path:
    """Return the current user's Downloads folder, creating it if needed."""
    candidates: list[Path] = []
    if sys.platform == "win32":
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
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if path.is_dir():
            return path

    raise DownloadsFolderError(
        "Could not find or create your Downloads folder. "
        "This app saves resumes there instead of downloading a zip."
    )


def save_resume_to_downloads(folder_name: str, file_name: str, source: Path) -> Path:
    """Create `{Downloads}/{folder_name}/` and copy `source` in as `file_name`.

    Returns the destination file path.
    """
    if not folder_name or not file_name:
        raise DownloadsFolderError("Missing folder or file name for the resume export.")
    if not source.is_file():
        raise DownloadsFolderError("The rendered resume file is missing.")

    dest_dir = resolve_downloads_dir() / folder_name
    dest_file = dest_dir / file_name
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest_file)
    except OSError as exc:
        raise DownloadsFolderError(f"Could not save the resume to Downloads: {exc}") from exc
    return dest_file


def reveal_folder(folder: Path) -> None:
    """Open the saved folder in Explorer (Windows) or the system file manager."""
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder)], check=False)
        else:
            subprocess.run(["xdg-open", str(folder)], check=False)
    except OSError:
        pass
