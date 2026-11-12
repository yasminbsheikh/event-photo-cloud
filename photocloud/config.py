"""Per-user storage: client credentials, OAuth tokens and cached images.

Everything lives under ~/.photocloud (override with PHOTOCLOUD_HOME).
Tokens are written with 0600 permissions and are never sent to the browser.
"""
import json
import os
import threading
from pathlib import Path


def home_dir() -> Path:
    path = Path(os.environ.get("PHOTOCLOUD_HOME", "~/.photocloud")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def write_private_json(path: Path, data: dict) -> None:
    """Atomic write, readable only by the current user."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def load_credentials(home: Path) -> dict:
    """OAuth client settings. Environment variables win over credentials.json.

    credentials.json: {"google": {"client_id": "...", "client_secret": "..."},
                       "dropbox": {"app_key": "..."}}
    """
    file_creds = read_json(home / "credentials.json")
    google = dict(file_creds.get("google", {}))
    dropbox = dict(file_creds.get("dropbox", {}))
    env = os.environ.get
    if env("PHOTOCLOUD_GOOGLE_CLIENT_ID"):
        google["client_id"] = env("PHOTOCLOUD_GOOGLE_CLIENT_ID")
    if env("PHOTOCLOUD_GOOGLE_CLIENT_SECRET"):
        google["client_secret"] = env("PHOTOCLOUD_GOOGLE_CLIENT_SECRET")
    if env("PHOTOCLOUD_DROPBOX_APP_KEY"):
        dropbox["app_key"] = env("PHOTOCLOUD_DROPBOX_APP_KEY")
    return {"google": google, "dropbox": dropbox}


class TokenStore:
    """Thread-safe JSON file with one token record per connection name."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def get(self, name: str) -> dict | None:
        with self.lock:
            return read_json(self.path).get(name)

    def set(self, name: str, token: dict) -> None:
        with self.lock:
            data = read_json(self.path)
            data[name] = token
            write_private_json(self.path, data)

    def delete(self, name: str) -> None:
        with self.lock:
            data = read_json(self.path)
            if data.pop(name, None) is not None:
                write_private_json(self.path, data)
