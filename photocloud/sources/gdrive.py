"""Google Drive folder (Drive API v3, read-only)."""
import re
import urllib.parse
from collections import deque

from ..errors import SourceError
from ..http import ApiError, request, request_json
from .base import ImageRef, Source

API = "https://www.googleapis.com/drive/v3"
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
FOLDER_MIME = "application/vnd.google-apps.folder"
MAX_FOLDERS = 200  # safety cap when walking subfolders


def parse_folder_id(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "root"
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", raw) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    if re.fullmatch(r"root|[A-Za-z0-9_-]{10,}", raw):
        return raw
    raise SourceError("Paste a Google Drive folder link or folder ID (leave blank for My Drive).")


class DriveSource(Source):
    kind = "gdrive"
    cacheable = True

    def __init__(self, raw_folder: str, recursive: bool, token_fn) -> None:
        self.folder_id = parse_folder_id(raw_folder)
        self.recursive = recursive
        self.token_fn = token_fn
        self.description = "Google Drive: " + ("My Drive" if self.folder_id == "root" else self.folder_id)
        self.empty_message = "No supported images (jpg, jpeg, png, webp) found in that Drive folder."

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token_fn()}"}

    def _children(self, folder_id: str):
        token = None
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": "nextPageToken, files(id,name,mimeType,md5Checksum,modifiedTime)",
                "pageSize": "1000", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            }
            if token:
                params["pageToken"] = token
            try:
                data = request_json("GET", f"{API}/files?{urllib.parse.urlencode(params)}",
                                    headers=self._headers())
            except ApiError as exc:
                if exc.status == 404:
                    raise SourceError("Drive folder not found (or not shared with your account).") from exc
                raise
            yield from data.get("files", [])
            token = data.get("nextPageToken")
            if not token:
                return

    def list_images(self) -> list[ImageRef]:
        refs, queue, seen = [], deque([self.folder_id]), 0
        while queue:
            folder = queue.popleft()
            seen += 1
            for f in self._children(folder):
                if f["mimeType"] in IMAGE_MIMES and not f["name"].startswith("."):
                    refs.append(ImageRef(f["id"], f["name"], f.get("md5Checksum") or f.get("modifiedTime", "")))
                elif f["mimeType"] == FOLDER_MIME and self.recursive and seen + len(queue) < MAX_FOLDERS:
                    queue.append(f["id"])
        return refs

    def fetch(self, ref: ImageRef) -> bytes:
        url = f"{API}/files/{urllib.parse.quote(ref.id)}?alt=media&supportsAllDrives=true"
        return request("GET", url, headers=self._headers())
