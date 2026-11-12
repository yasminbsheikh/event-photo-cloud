"""Local-only HTTP server: static frontend + a small JSON/image API.

Images are served only by numeric id from the scanned list, so the browser can
never request arbitrary paths. The server binds to 127.0.0.1 only, rejects
requests with a foreign Host/Origin header, and never exposes OAuth tokens.
"""
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .cache import sniff_image_type
from .config import TokenStore, home_dir, load_credentials
from .cache import DiskCache
from .errors import AuthRequired, SourceError
from .http import ApiError
from .oauth import PROVIDERS, OAuthManager
from .sources import Context, build_source
from .sources.gphotos import PhotosPicker

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("text/javascript", ".js")

CALLBACK_PAGE = """<!doctype html><meta charset="utf-8"><title>Photo Cloud</title>
<body style="font:16px system-ui;background:#111;color:#ddd;text-align:center;padding-top:20vh">
<h2>{title}</h2><p>{body}</p><script>{script}</script></body>"""


def make_context(port: int) -> Context:
    home = home_dir()
    tokens = TokenStore(home / "tokens.json")
    port_ref = {"port": port} 
    auth = OAuthManager(tokens, lambda: load_credentials(home),
                        lambda: f"http://127.0.0.1:{port_ref['port']}/oauth/callback")
    picker = PhotosPicker(lambda: auth.access_token("gphotos"), home / "gphotos")
    return Context(home=home, auth=auth, cache=DiskCache(home / "cache"), picker=picker,
                   port_ref=port_ref)

class AppState:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.lock = threading.Lock()
        self.source = None
        self.refs: list = []
        self.generation = 0     # part of image URLs so the browser never serves stale cache

    def load(self, kind: str, params: dict) -> int:
        source = build_source(kind, params, self.ctx)
        refs = source.list_images()
        if not refs:
            raise SourceError(source.empty_message)
        with self.lock:
            self.source, self.refs = source, refs
            self.generation += 1
        return len(refs)

    def snapshot(self):
        with self.lock:
            return self.source, list(self.refs), self.generation

    def image_bytes(self, source, ref) -> bytes:
        if not source.cacheable:
            return source.fetch(ref)
        key = f"{source.kind}:{ref.id}:{ref.version}"
        data = self.ctx.cache.get(key)
        if data is None:
            data = source.fetch(ref)
            self.ctx.cache.put(key, data)
        return data


def make_handler(state: AppState):
    ctx = state.ctx

    class Handler(BaseHTTPRequestHandler):
        server_version = "PhotoCloud/2.0"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        # -- helpers -------------------------------------------------------
        def _send(self, status, body: bytes, ctype, cache="no-store", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, status=200):
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _error(self, exc: Exception):
            if isinstance(exc, AuthRequired):
                return self._json({"error": str(exc), "auth": exc.provider}, 401)
            status = 502 if isinstance(exc, ApiError) else 400
            self._json({"error": str(exc)}, status)

        def _file(self, path: Path, cache="no-cache"):
            try:
                data = path.read_bytes()
            except OSError:
                return self._json({"error": "File not readable"}, 404)
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send(200, data, ctype, cache)

        def _local_request_ok(self) -> bool:
            """Blocks DNS-rebinding and cross-site requests to this local server."""
            port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host", "") not in allowed:
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in {f"http://{h}" for h in allowed}
        
        # -- routes --------------------------------------------------------
        def do_GET(self):
            if not self._local_request_ok():
                return self._json({"error": "Forbidden"}, 403)
            url = urlparse(self.path)
            path = unquote(url.path)
            try:
                if path == "/api/state":
                    return self._json(self._state_payload())
                if path == "/api/images":
                    _, refs, gen = state.snapshot()
                    return self._json({"images": [
                        {"id": i, "name": r.name, "url": f"/img/{i}?g={gen}"} for i, r in enumerate(refs)]})
                if path.startswith("/img/"):
                    return self._image(path[5:])
                if path.startswith("/oauth/start/"):
                    return self._oauth_start(path.rsplit("/", 1)[1])
                if path == "/oauth/callback":
                    return self._oauth_callback(parse_qs(url.query))
                if path == "/api/gphotos/status":
                    return self._json(ctx.picker.status())
            except (SourceError, ApiError) as exc:
                return self._error(exc)
            # static frontend
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (WEB_DIR / rel).resolve()
            if WEB_DIR in target.parents and target.is_file():
                return self._file(target)
            self._json({"error": "Not found"}, 404)

        def do_POST(self):
            if not self._local_request_ok():
                return self._json({"error": "Forbidden"}, 403)
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json({"error": "Bad request"}, 400)
            try:
                if path == "/api/source":
                    kind = str(body.get("kind", "local"))
                    count = state.load(kind, body)
                    return self._json({"ok": True, "count": count, **self._state_payload()})
                if path == "/api/disconnect":
                    if body.get("provider") not in PROVIDERS:
                        return self._json({"error": "Unknown provider"}, 400)
                    ctx.auth.disconnect(body["provider"])
                    return self._json({"ok": True})
                if path == "/api/gphotos/start":
                    return self._json({"pickerUri": ctx.picker.start()})
            except (SourceError, ApiError) as exc:
                return self._error(exc)
            self._json({"error": "Not found"}, 404)

        # -- pieces --------------------------------------------------------
        def _state_payload(self):
            source, refs, _ = state.snapshot()
            return {
                "kind": source.kind if source else "",
                "description": source.description if source else "",
                "count": len(refs),
                "connected": {n: ctx.auth.is_connected(n) for n in PROVIDERS},
                "configured": ctx.auth.configured(),
                "gphotos_saved": (ctx.home / "gphotos" / "index.json").is_file(),
            }

        def _image(self, tail: str):
            source, refs, _ = state.snapshot()
            try:
                ref = refs[int(tail)]
                data = state.image_bytes(source, ref)
            except (ValueError, IndexError):
                return self._json({"error": "Unknown image"}, 404)
            except (OSError, SourceError, ApiError):
                return self._json({"error": "Image could not be loaded"}, 502)
            self._send(200, data, sniff_image_type(data), cache="max-age=3600")

        def _oauth_start(self, name: str):
            url = ctx.auth.start(name)
            self._send(302, b"", "text/plain", extra={"Location": url})

        def _oauth_callback(self, q):
            def page(title, body, ok):
                script = "setTimeout(()=>window.close(),1200)" if ok else ""
                self._send(200, CALLBACK_PAGE.format(title=title, body=body, script=script).encode(),
                           "text/html; charset=utf-8")
            if "error" in q:
                return page("Not connected", "Access was not granted. You can close this tab.", False)
            try:
                name = ctx.auth.finish(q.get("state", [""])[0], q.get("code", [""])[0])
            except SourceError as exc:
                msg = str(exc).replace("<", "&lt;")
                return page("Connection failed", msg, False)
            page("Connected", f"{PROVIDERS[name].label} is connected. You can close this tab.", True)

    return Handler


def serve(host: str, port: int, state: AppState) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(state))
