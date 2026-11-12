from pathlib import Path

from ..images import resolve_folder, scan_folder
from .base import ImageRef, Source


class LocalSource(Source):
    kind = "local"

    def __init__(self, raw_path: str, recursive: bool = False) -> None:
        self.folder = resolve_folder(raw_path)
        self.recursive = recursive
        self.description = str(self.folder)
        self.empty_message = f"No supported images (jpg, jpeg, png, webp) found in: {self.folder}"

    def list_images(self) -> list[ImageRef]:
        return [ImageRef(id=str(p), name=p.name) for p in scan_folder(self.folder, self.recursive)]

    def fetch(self, ref: ImageRef) -> bytes:
        return Path(ref.id).read_bytes()
