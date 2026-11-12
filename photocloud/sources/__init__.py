"""Photo sources: local folder, Google Drive, Dropbox, Google Photos (picked)."""
from dataclasses import dataclass, field
from pathlib import Path

from ..cache import DiskCache
from ..errors import SourceError
from ..oauth import OAuthManager
from .base import ImageRef, Source
from .dropbox import DropboxSource
from .gdrive import DriveSource
from .gphotos import GooglePhotosSource, PhotosPicker
from .local import LocalSource

KINDS = ("local", "gphotos", "gdrive", "dropbox")


@dataclass
class Context:
    home: Path
    auth: OAuthManager
    cache: DiskCache
    picker: PhotosPicker
    port_ref: dict = field(default_factory=lambda: {"port": 0})  # real port, known after bind

def build_source(kind: str, params: dict, ctx: Context) -> Source:
    recursive = bool(params.get("recursive"))
    path = str(params.get("path", ""))
    if kind == "local":
        return LocalSource(path, recursive)
    if kind == "gdrive":
        ctx.auth.access_token("gdrive")        # raises AuthRequired when not connected
        return DriveSource(path, recursive, lambda: ctx.auth.access_token("gdrive"))
    if kind == "dropbox":
        ctx.auth.access_token("dropbox")
        return DropboxSource(path, recursive, lambda: ctx.auth.access_token("dropbox"))
    if kind == "gphotos":
        return GooglePhotosSource(ctx.home / "gphotos")
    raise SourceError(f"Unknown photo source: {kind}")


__all__ = ["Context", "ImageRef", "Source", "build_source", "KINDS"]
