"""On-disk cache for images fetched from cloud services, plus image sniffing."""
import hashlib
from pathlib import Path


def sniff_image_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


class DiskCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.root / digest[:2] / digest

    def get(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except OSError:
            return None

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def clear(self) -> int:
        n = 0
        for p in self.root.rglob("*"):
            if p.is_file():
                p.unlink(missing_ok=True)
                n += 1
        return n
