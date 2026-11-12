"""OAuth 2.0 (authorization code + PKCE, loopback redirect) for Google and Dropbox.

Flow: the browser opens /oauth/start/<name> -> provider consent page ->
http://127.0.0.1:<port>/oauth/callback -> we exchange the code for tokens and
keep them in TokenStore. Access tokens are refreshed automatically.
"""
import base64
import hashlib
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from .config import TokenStore
from .errors import AuthRequired, SourceError
from .http import ApiError, request_json


@dataclass(frozen=True)
class Provider:
    name: str            # token key
    label: str
    cred_key: str        # section of credentials.json
    auth_url: str
    token_url: str
    scope: str
    extra_auth: dict = field(default_factory=dict)


GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"

PROVIDERS = {
    "gdrive": Provider("gdrive", "Google Drive", "google", GOOGLE_AUTH, GOOGLE_TOKEN,
                       "https://www.googleapis.com/auth/drive.readonly",
                       {"access_type": "offline", "prompt": "consent"}),
    "gphotos": Provider("gphotos", "Google Photos", "google", GOOGLE_AUTH, GOOGLE_TOKEN,
                        "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
                        {"access_type": "offline", "prompt": "consent"}),
    "dropbox": Provider("dropbox", "Dropbox", "dropbox",
                        "https://www.dropbox.com/oauth2/authorize",
                        "https://api.dropboxapi.com/oauth2/token",
                        "files.metadata.read files.content.read",
                        {"token_access_type": "offline"}),
}


def _client_id(provider: Provider, creds: dict) -> str:
    section = creds.get(provider.cred_key, {})
    key = "app_key" if provider.cred_key == "dropbox" else "client_id"
    if not section.get(key):
        raise SourceError(
            f"No {provider.label} {key} configured. Add it to credentials.json in "
            "your Photo Cloud folder (see README: Cloud setup).")
    return section[key]


class OAuthManager:
    def __init__(self, tokens: TokenStore, load_creds, redirect_uri_fn) -> None:
        self.tokens = tokens
        self.load_creds = load_creds            # callable -> dict (re-read each time)
        self.redirect_uri_fn = redirect_uri_fn  # callable -> str
        self.pending: dict[str, tuple[str, str, float]] = {}
        self.lock = threading.Lock()
        self.refresh_lock = threading.Lock()

    # -- status ------------------------------------------------------------
    def is_connected(self, name: str) -> bool:
        return self.tokens.get(name) is not None

    def configured(self) -> dict:
        creds = self.load_creds()
        return {"google": bool(creds["google"].get("client_id")),
                "dropbox": bool(creds["dropbox"].get("app_key"))}

    def disconnect(self, name: str) -> None:
        self.tokens.delete(name)

    # -- authorization -----------------------------------------------------
    def start(self, name: str) -> str:
        provider = PROVIDERS.get(name)
        if not provider:
            raise SourceError("Unknown provider.")
        client_id = _client_id(provider, self.load_creds())
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(24)
        with self.lock:
            now = time.time()
            self.pending = {s: v for s, v in self.pending.items() if now - v[2] < 600}
            self.pending[state] = (name, verifier, now)
        params = {
            "client_id": client_id, "response_type": "code", "scope": provider.scope,
            "redirect_uri": self.redirect_uri_fn(), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256", **provider.extra_auth,
        }
        return provider.auth_url + "?" + urllib.parse.urlencode(params)

    def finish(self, state: str, code: str) -> str:
        with self.lock:
            entry = self.pending.pop(state, None)
        if not entry:
            raise SourceError("This sign-in link has expired. Start the connection again.")
        name, verifier, _ = entry
        provider = PROVIDERS[name]
        creds = self.load_creds()
        form = {"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                "redirect_uri": self.redirect_uri_fn(), "client_id": _client_id(provider, creds)}
        if provider.cred_key == "google" and creds["google"].get("client_secret"):
            form["client_secret"] = creds["google"]["client_secret"]
        data = request_json("POST", provider.token_url, form=form)
        self._store(name, data, old=None)
        return name

    def _store(self, name: str, data: dict, old: dict | None) -> dict:
        refresh = data.get("refresh_token") or (old or {}).get("refresh_token")
        if not data.get("access_token"):
            raise SourceError("The service did not return an access token.")
        token = {"access_token": data["access_token"], "refresh_token": refresh,
                 "expires_at": time.time() + float(data.get("expires_in", 3600))}
        self.tokens.set(name, token)
        return token

    # -- using tokens ------------------------------------------------------
    def access_token(self, name: str) -> str:
        provider = PROVIDERS[name]
        token = self.tokens.get(name)
        if not token:
            raise AuthRequired(name, f"Connect {provider.label} first.")
        if token["expires_at"] - 60 > time.time():
            return token["access_token"]
        with self.refresh_lock:
            token = self.tokens.get(name)            # another thread may have refreshed
            if not token:
                raise AuthRequired(name, f"Connect {provider.label} first.")
            if token["expires_at"] - 60 > time.time():
                return token["access_token"]
            if not token.get("refresh_token"):
                self.tokens.delete(name)
                raise AuthRequired(name, f"{provider.label} sign-in expired. Connect again.")
            creds = self.load_creds()
            form = {"grant_type": "refresh_token", "refresh_token": token["refresh_token"],
                    "client_id": _client_id(provider, creds)}
            if provider.cred_key == "google" and creds["google"].get("client_secret"):
                form["client_secret"] = creds["google"]["client_secret"]
            try:
                data = request_json("POST", provider.token_url, form=form)
            except ApiError as exc:
                if exc.status in (400, 401):         # revoked / expired refresh token
                    self.tokens.delete(name)
                    raise AuthRequired(name, f"{provider.label} sign-in expired. Connect again.") from exc
                raise
            return self._store(name, data, old=token)["access_token"]
