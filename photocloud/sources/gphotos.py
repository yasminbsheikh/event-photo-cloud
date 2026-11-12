"""Google Photos via the Picker API.

Since 31 March 2025 Google no longer lets apps browse a user's library or
albums. Instead the user picks photos in Google's own picker UI. We download
the picked photos once (~2048px) into ~/.photocloud/gphotos/ so the selection
keeps working on later runs without picking again.
"""
import hashlib
import json
import shutil
import threading
import time
import urllib.parse
from pathlib import Path

from ..config import read_json
from ..errors import SourceError
from ..http import ApiError, request, request_json
from .base import ImageRef, Source

PICKER = "https://photospicker.googleapis.com/v1"
SIZE = "=w2048-h2048"


def _seconds(value, default: float) -> float:
    try:
        return float(str(value).rstrip("s"))
    except (TypeError, ValueError):
        return default


class GooglePhotosSource(Source):
    kind = "gphotos"

    def __init__(self, store_dir: Path) -> None:
        self.dir = store_dir
        self.items = read_json(store_dir / "index.json").get("items", [])
        self.description = f"Google Photos: {len(self.items)} picked photos"
        self.empty_message = "No Google Photos selection yet. Choose photos first."

    def list_images(self) -> list[ImageRef]:
        return [ImageRef(i["file"], i["name"]) for i in self.items]

    def fetch(self, ref: ImageRef) -> bytes:
        if "/" in ref.id or "\\" in ref.id:
            raise SourceError("Bad image id.")
        return (self.dir / ref.id).read_bytes()


class PhotosPicker:
    """Runs one picking session: create -> user picks -> poll -> download."""

    def __init__(self, token_fn, store_dir: Path, max_items: int = 200) -> None:
        self.token_fn, self.dir, self.max_items = token_fn, store_dir, max_items
        self.lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.state = "idle"       # idle | waiting | downloading | done | error
        self.message = ""
        self.session_id = None
        self.poll_seconds = 5.0
        self.deadline = 0.0
        self.last_poll = 0.0
        self.done = self.total = 0

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token_fn()}"}

    def start(self) -> str:
        with self.lock:
            if self.state in ("waiting", "downloading"):
                raise SourceError("A Google Photos selection is already in progress.")
            self._reset()
            session = request_json("POST", f"{PICKER}/sessions", headers=self._h(),
                                   json_body={"pickingConfig": {"maxItemCount": str(self.max_items)}})
            cfg = session.get("pollingConfig", {})
            self.session_id = session["id"]
            self.poll_seconds = max(_seconds(cfg.get("pollInterval"), 5.0), 2.0)
            self.deadline = time.time() + _seconds(cfg.get("timeoutIn"), 600.0)
            self.state = "waiting"
            self.message = "Choose photos in the Google Photos tab, then press Done there."
            return session["pickerUri"].rstrip("/") + "/autoclose"

    def status(self) -> dict:
        with self.lock:
            if self.state == "waiting":
                if time.time() > self.deadline:
                    self.state, self.message = "error", "The Google Photos picker timed out. Try again."
                elif time.time() - self.last_poll >= self.poll_seconds * 0.9:
                    self.last_poll = time.time()
                    try:
                        info = request_json("GET", f"{PICKER}/sessions/{self.session_id}", headers=self._h())
                        if info.get("mediaItemsSet"):
                            self.state, self.message = "downloading", "Downloading your selection…"
                            threading.Thread(target=self._download, daemon=True).start()
                    except SourceError as exc:
                        self.state, self.message = "error", str(exc)
            return {"state": self.state, "message": self.message, "done": self.done,
                    "total": self.total, "poll_seconds": self.poll_seconds}

    def _download(self) -> None:
        try:
            picked, page = [], None
            while len(picked) < self.max_items:
                q = {"sessionId": self.session_id, "pageSize": "100"}
                if page:
                    q["pageToken"] = page
                data = request_json("GET", f"{PICKER}/mediaItems?{urllib.parse.urlencode(q)}", headers=self._h())
                for it in data.get("mediaItems", []):
                    mf = it.get("mediaFile", {})
                    if it.get("type", "PHOTO") == "PHOTO" and mf.get("baseUrl") \
                            and mf.get("mimeType", "image/").startswith("image/"):
                        picked.append((it["id"], mf.get("filename") or it["id"], mf["baseUrl"]))
                page = data.get("nextPageToken")
                if not page:
                    break
            picked = picked[: self.max_items]
            if not picked:
                raise SourceError("No photos were selected (videos are skipped).")
            with self.lock:
                self.total = len(picked)
            self.dir.mkdir(parents=True, exist_ok=True)
            items = []
            for n, (pid, name, base) in enumerate(picked, 1):
                fname = hashlib.sha1(pid.encode()).hexdigest()[:20]
                try:   # picker base URLs need the OAuth header too
                    (self.dir / fname).write_bytes(request("GET", base + SIZE, headers=self._h()))
                    items.append({"file": fname, "name": name})
                except SourceError:
                    pass                                   # skip one bad photo, keep going
                with self.lock:
                    self.done = n
            if not items:
                raise SourceError("None of the selected photos could be downloaded.")
            keep = {i["file"] for i in items} | {"index.json"}
            for p in self.dir.iterdir():
                if p.name not in keep:
                    p.unlink(missing_ok=True) if p.is_file() else shutil.rmtree(p, ignore_errors=True)
            (self.dir / "index.json").write_text(json.dumps({"items": items, "picked_at": time.time()}))
            try:
                request("DELETE", f"{PICKER}/sessions/{self.session_id}", headers=self._h())
            except SourceError:
                pass
            with self.lock:
                self.state, self.message = "done", f"Saved {len(items)} photos."
        except SourceError as exc:
            with self.lock:
                self.state, self.message = "error", str(exc)
        except Exception as exc:   # never leave the UI stuck on "downloading"
            with self.lock:
                self.state, self.message = "error", f"Unexpected error: {exc}"
