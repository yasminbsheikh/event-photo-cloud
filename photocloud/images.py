"""Folder discovery for supported image files."""
from pathlib import Path

from .errors import SourceError

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class FolderError(SourceError):
    """Raised when a folder cannot be used; the message is shown to the user."""


def resolve_folder(raw: str) -> Path:
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        raise FolderError("Please enter a folder path.")
    folder = Path(raw).expanduser()
    try:
        folder = folder.resolve()
    except OSError as exc:
        raise FolderError(f"Cannot resolve path: {exc}") from exc
    if not folder.exists():
        raise FolderError(f"Folder not found: {folder}")
    if not folder.is_dir():
        raise FolderError(f"Not a folder: {folder}")
    return folder


def scan_folder(folder: Path, recursive: bool = False) -> list[Path]:
    """Return supported image files in the folder, sorted by path."""
    try:
        entries = folder.rglob("*") if recursive else folder.iterdir()
        files = [
            p for p in entries
            if p.suffix.lower() in SUPPORTED_EXTENSIONS
            and not p.name.startswith(".")
            and p.is_file()
        ]
    except PermissionError as exc:
        raise FolderError(f"Permission denied reading: {folder}") from exc
    except OSError as exc:
        raise FolderError(f"Cannot read folder: {exc}") from exc
    return sorted(files)
