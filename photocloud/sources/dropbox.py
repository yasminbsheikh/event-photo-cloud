"""Dropbox folder (API v2, read-only)."""
import json

from ..errors import SourceError
from ..http import ApiError, request, request_json
from .base import ImageRef, Source

API = "https://api.dropboxapi.com/2"
CONTENT = "https://content.dropboxapi.com/2"
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def normalize_path(raw: str) -> str:
    raw = (raw or "").strip().strip('"').strip("'")
    if raw in ("", "/"):
        return ""                       # Dropbox's API spells the root as ""
    return "/" + raw.strip("/")


class DropboxSource(Source):
    kind = "dropbox"
    cacheable = True

    def __init__(self, raw_path: str, recursive: bool, token_fn) -> None:
        self.path = normalize_path(raw_path)
        self.recursive = recursive
        self.token_fn = token_fn
        self.description = "Dropbox: " + (self.path or "/")
        self.empty_message = f"No supported images (jpg, jpeg, png, webp) found in Dropbox folder {self.path or '/'}."

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token_fn()}"}

    def list_images(self) -> list[ImageRef]:
        refs = []
        try:
            data = request_json("POST", f"{API}/files/list_folder", headers=self._auth(),
                                json_body={"path": self.path, "recursive": self.recursive, "limit": 2000})
            while True:
                for e in data.get("entries", []):
                    if e.get(".tag") == "file" and e["name"].lower().endswith(EXTENSIONS) \
                            and not e["name"].startswith("."):
                        refs.append(ImageRef(e["id"], e["name"], e.get("rev", "")))
                if not data.get("has_more"):
                    break
                data = request_json("POST", f"{API}/files/list_folder/continue", headers=self._auth(),
                                    json_body={"cursor": data["cursor"]})
        except ApiError as exc:
            if exc.status == 409 and "not_found" in exc.detail:
                raise SourceError(f"Dropbox folder not found: {self.path or '/'}") from exc
            if exc.status == 409 and "not_folder" in exc.detail:
                raise SourceError(f"That Dropbox path is not a folder: {self.path}") from exc
            raise
        return sorted(refs, key=lambda r: r.name.lower())

    def fetch(self, ref: ImageRef) -> bytes:
        # A 2048px JPEG thumbnail is far lighter than a multi-MB original and is
        # plenty for the cloud; fall back to the original if Dropbox refuses.
        arg = {"resource": {".tag": "path", "path": ref.id}, "format": {".tag": "jpeg"},
               "size": {".tag": "w2048h1536"}, "mode": {".tag": "strict"}}
        try:
            return request("POST", f"{CONTENT}/files/get_thumbnail_v2",
                           headers={**self._auth(), "Dropbox-API-Arg": json.dumps(arg)})
        except ApiError:
            return request("POST", f"{CONTENT}/files/download",
                           headers={**self._auth(), "Dropbox-API-Arg": json.dumps({"path": ref.id})})
