"""Cloud sources, OAuth and server tests against a mock HTTP service (no network needed)."""
import dataclasses
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from photocloud import oauth
from photocloud.cache import DiskCache
from photocloud.config import TokenStore
from photocloud.errors import AuthRequired, SourceError
from photocloud.oauth import OAuthManager
from photocloud.server import AppState, serve
from photocloud.sources import Context, build_source, dropbox, gdrive, gphotos
from photocloud.sources.gphotos import PhotosPicker

JPEG = b"\xff\xd8\xff" + b"jpegdata"


class Mock(BaseHTTPRequestHandler):
    """Pretends to be Drive, Dropbox, Google Photos Picker and the token endpoints."""
    log = []
    picked = False
    token_calls = 0
    refresh_ok = True

    def log_message(self, *a): pass

    def _reply(self, obj=None, status=200, raw=None):
        body = raw if raw is not None else json.dumps(obj or {}).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        Mock.log.append((self.command, u.path, dict(self.headers), body))
        p = u.path
        if p == "/token":
            Mock.token_calls += 1
            form = urllib.parse.parse_qs(body.decode())
            if form["grant_type"] == ["refresh_token"] and not Mock.refresh_ok:
                return self._reply({"error": "invalid_grant"}, 400)
            return self._reply({"access_token": f"at{Mock.token_calls}", "expires_in": 3600,
                                **({"refresh_token": "rt"} if form["grant_type"] == ["authorization_code"] else {})})
        # Drive
        if p == "/drive/v3/files" and self.command == "GET":
            query = q["q"][0]
            if "'root'" in query:
                if "pageToken" not in q:
                    return self._reply({"files": [
                        {"id": "f1", "name": "a.jpg", "mimeType": "image/jpeg", "md5Checksum": "m1"},
                        {"id": "d1", "name": "sub", "mimeType": gdrive.FOLDER_MIME},
                        {"id": "t", "name": "notes.txt", "mimeType": "text/plain"}], "nextPageToken": "p2"})
                return self._reply({"files": [{"id": "f2", "name": "b.png", "mimeType": "image/png"}]})
            if "'d1'" in query:
                return self._reply({"files": [{"id": "f3", "name": "c.webp", "mimeType": "image/webp"}]})
            return self._reply({"error": "nf"}, 404)
        if p.startswith("/drive/v3/files/"):
            return self._reply(raw=JPEG + p.rsplit("/", 1)[1].encode())
        # Dropbox
        if p == "/2/files/list_folder":
            arg = json.loads(body)
            if arg["path"] == "/missing":
                return self._reply({"error_summary": "path/not_found/.."}, 409)
            return self._reply({"entries": [
                {".tag": "file", "name": "z.jpg", "id": "id:1", "rev": "r1"},
                {".tag": "folder", "name": "dir", "id": "id:d"}], "has_more": True, "cursor": "c1"})
        if p == "/2/files/list_folder/continue":
            return self._reply({"entries": [{".tag": "file", "name": "A.PNG", "id": "id:2", "rev": "r2"},
                                            {".tag": "file", "name": "doc.pdf", "id": "id:3"}], "has_more": False})
        if p == "/2/files/get_thumbnail_v2":
            arg = json.loads(self.headers["Dropbox-API-Arg"])
            if arg["resource"]["path"] == "id:2":
                return self._reply({"error_summary": "unsupported_image"}, 409)
            return self._reply(raw=JPEG + b"thumb")
        if p == "/2/files/download":
            return self._reply(raw=JPEG + b"full")
        # Picker
        if p == "/v1/sessions" and self.command == "POST":
            return self._reply({"id": "S1", "pickerUri": "https://photos.example/pick/S1",
                                "pollingConfig": {"pollInterval": "0.01s", "timeoutIn": "60s"}})
        if p == "/v1/sessions/S1" and self.command == "GET":
            return self._reply({"id": "S1", "mediaItemsSet": Mock.picked})
        if p == "/v1/sessions/S1" and self.command == "DELETE":
            return self._reply({})
        if p == "/v1/mediaItems":
            return self._reply({"mediaItems": [
                {"id": "m1", "type": "PHOTO", "mediaFile": {"baseUrl": self.base + "/img/1", "mimeType": "image/jpeg", "filename": "one.jpg"}},
                {"id": "m2", "type": "VIDEO", "mediaFile": {"baseUrl": self.base + "/img/2", "mimeType": "video/mp4", "filename": "v.mp4"}},
                {"id": "m3", "type": "PHOTO", "mediaFile": {"baseUrl": self.base + "/img/3", "mimeType": "image/jpeg", "filename": "three.jpg"}}]})
        if p.startswith("/img/"):
            return self._reply(raw=JPEG + p.encode())
        self._reply({"error": "unhandled " + p}, 404)

    do_GET = do_POST = do_DELETE = _handle


class CloudTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        cls.base = f"http://127.0.0.1:{cls.mock.server_address[1]}"
        Mock.base = cls.base
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()
        cls._saved = (gdrive.API, dropbox.API, dropbox.CONTENT, gphotos.PICKER, dict(oauth.PROVIDERS))
        gdrive.API, dropbox.API, dropbox.CONTENT = cls.base + "/drive/v3", cls.base + "/2", cls.base + "/2"
        gphotos.PICKER = cls.base + "/v1"
        for name, p in list(oauth.PROVIDERS.items()):
            oauth.PROVIDERS[name] = dataclasses.replace(p, token_url=cls.base + "/token")

    @classmethod
    def tearDownClass(cls):
        cls.mock.shutdown()
        gdrive.API, dropbox.API, dropbox.CONTENT, gphotos.PICKER, providers = cls._saved
        oauth.PROVIDERS.clear(); oauth.PROVIDERS.update(providers)

    def setUp(self):
        Mock.log, Mock.picked, Mock.token_calls, Mock.refresh_ok = [], False, 0, True
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.tokens = TokenStore(self.home / "tokens.json")
        creds = {"google": {"client_id": "gid", "client_secret": "gsec"}, "dropbox": {"app_key": "dkey"}}
        self.auth = OAuthManager(self.tokens, lambda: creds, lambda: "http://127.0.0.1:1/oauth/callback")
        self.picker = PhotosPicker(lambda: self.auth.access_token("gphotos"), self.home / "gphotos")
        self.ctx = Context(self.home, self.auth, DiskCache(self.home / "cache"), self.picker)

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self, *names):
        for n in names:
            self.tokens.set(n, {"access_token": "tok-" + n, "refresh_token": "rt", "expires_at": time.time() + 3600})


class DriveTests(CloudTestCase):
    def test_folder_id_parsing(self):
        self.assertEqual(gdrive.parse_folder_id(""), "root")
        self.assertEqual(gdrive.parse_folder_id("https://drive.google.com/drive/folders/1AbC_dEf-GhIjK?usp=sharing"), "1AbC_dEf-GhIjK")
        self.assertEqual(gdrive.parse_folder_id("https://drive.google.com/open?id=1AbC_dEf-GhIjK"), "1AbC_dEf-GhIjK")
        with self.assertRaises(SourceError):
            gdrive.parse_folder_id("not a folder!")

    def test_requires_connection(self):
        with self.assertRaises(AuthRequired) as cm:
            build_source("gdrive", {}, self.ctx)
        self.assertEqual(cm.exception.provider, "gdrive")

    def test_list_paginates_recurses_and_fetches(self):
        self.connect("gdrive")
        flat = build_source("gdrive", {"path": "", "recursive": False}, self.ctx)
        self.assertEqual([r.name for r in flat.list_images()], ["a.jpg", "b.png"])
        deep = build_source("gdrive", {"path": "", "recursive": True}, self.ctx)
        refs = deep.list_images()
        self.assertEqual(sorted(r.name for r in refs), ["a.jpg", "b.png", "c.webp"])
        self.assertTrue(deep.fetch(refs[0]).startswith(b"\xff\xd8\xff"))
        auth_headers = {h["Authorization"] for _, _, h, _ in Mock.log if "Authorization" in h}
        self.assertEqual(auth_headers, {"Bearer tok-gdrive"})


class DropboxTests(CloudTestCase):
    def test_path_normalisation(self):
        self.assertEqual([dropbox.normalize_path(x) for x in ("", "/", "Photos/", " /a/b ")], ["", "", "/Photos", "/a/b"])

    def test_list_pagination_filter_and_fetch_fallback(self):
        self.connect("dropbox")
        src = build_source("dropbox", {"path": "/Photos", "recursive": True}, self.ctx)
        refs = src.list_images()
        self.assertEqual([r.name for r in refs], ["A.PNG", "z.jpg"])        # pdf and folder skipped
        self.assertEqual(src.fetch(refs[1]), JPEG + b"thumb")              # thumbnail path
        self.assertEqual(src.fetch(refs[0]), JPEG + b"full")               # thumbnail refused -> original

    def test_missing_folder_message(self):
        self.connect("dropbox")
        src = build_source("dropbox", {"path": "/missing"}, self.ctx)
        with self.assertRaisesRegex(SourceError, "not found"):
            src.list_images()


class OAuthTests(CloudTestCase):
    def test_start_uses_pkce_and_finish_stores_tokens(self):
        url = urllib.parse.urlparse(self.auth.start("gdrive"))
        q = urllib.parse.parse_qs(url.query)
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["client_id"], ["gid"])
        self.assertIn("drive.readonly", q["scope"][0])
        self.assertEqual(self.auth.finish(q["state"][0], "CODE"), "gdrive")
        self.assertEqual(self.tokens.get("gdrive")["refresh_token"], "rt")
        token_req = [b for m, p, h, b in Mock.log if p == "/token"][0].decode()
        self.assertIn("code_verifier=", token_req)
        self.assertIn("client_secret=gsec", token_req)

    def test_state_is_single_use_and_checked(self):
        state = urllib.parse.parse_qs(urllib.parse.urlparse(self.auth.start("dropbox")).query)["state"][0]
        with self.assertRaises(SourceError):
            self.auth.finish("forged", "CODE")
        self.auth.finish(state, "CODE")
        with self.assertRaises(SourceError):
            self.auth.finish(state, "CODE")

    def test_dropbox_sends_no_secret(self):
        state = urllib.parse.parse_qs(urllib.parse.urlparse(self.auth.start("dropbox")).query)["state"][0]
        self.auth.finish(state, "CODE")
        self.assertNotIn("client_secret", [b for m, p, h, b in Mock.log if p == "/token"][0].decode())

    def test_refresh_when_expired_and_revoked(self):
        self.tokens.set("gdrive", {"access_token": "old", "refresh_token": "rt", "expires_at": time.time() - 5})
        self.assertEqual(self.auth.access_token("gdrive"), "at1")
        self.assertEqual(self.tokens.get("gdrive")["refresh_token"], "rt")   # kept
        self.tokens.set("gdrive", {"access_token": "old", "refresh_token": "rt", "expires_at": time.time() - 5})
        Mock.refresh_ok = False
        with self.assertRaises(AuthRequired):
            self.auth.access_token("gdrive")
        self.assertIsNone(self.tokens.get("gdrive"))

    def test_missing_client_credentials(self):
        auth = OAuthManager(self.tokens, lambda: {"google": {}, "dropbox": {}}, lambda: "x")
        with self.assertRaisesRegex(SourceError, "credentials"):
            auth.start("gdrive")


class PhotosPickerTests(CloudTestCase):
    def wait_for(self, state):
        for _ in range(200):
            s = self.picker.status()
            if s["state"] == state:
                return s
            time.sleep(0.02)
        self.fail(f"picker never reached {state}: {s}")

    def test_full_flow(self):
        self.connect("gphotos")
        uri = self.picker.start()
        self.assertEqual(uri, "https://photos.example/pick/S1/autoclose")
        self.picker.poll_seconds = 0.01
        self.assertEqual(self.wait_for("waiting")["state"], "waiting")
        Mock.picked = True
        self.wait_for("done")
        src = build_source("gphotos", {}, self.ctx)
        refs = src.list_images()
        self.assertEqual(sorted(r.name for r in refs), ["one.jpg", "three.jpg"])   # video skipped
        self.assertTrue(src.fetch(refs[0]).startswith(b"\xff\xd8\xff"))
        img_calls = [(p, h) for _, p, h, _ in Mock.log if p.startswith("/img/")]
        self.assertEqual(len(img_calls), 2)
        self.assertTrue(all(h["Authorization"] == "Bearer tok-gphotos" for _, h in img_calls))
        self.assertTrue(any(m == "DELETE" for m, *_ in Mock.log))                  # session cleaned up

    def test_not_connected(self):
        with self.assertRaises(AuthRequired):
            self.picker.start()

    def test_fetch_rejects_path_tricks(self):
        src = gphotos.GooglePhotosSource(self.home / "gphotos")
        with self.assertRaises(SourceError):
            src.fetch(gphotos.ImageRef("../tokens.json", "x"))


class ServerTests(CloudTestCase):
    def setUp(self):
        super().setUp()
        self.state = AppState(self.ctx)
        self.httpd = serve("127.0.0.1", 0, self.state)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.photos = self.home / "photos"
        self.photos.mkdir()
        (self.photos / "a.jpg").write_bytes(JPEG + b"A")

    def tearDown(self):
        self.httpd.shutdown()
        super().tearDown()

    def call(self, path, body=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {},
                                     data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_local_source_and_image_url_generation(self):
        status, data, _ = self.call("/api/source", {"kind": "local", "path": str(self.photos)})
        self.assertEqual(status, 200)
        _, data, _ = self.call("/api/images")
        url = json.loads(data)["images"][0]["url"]
        self.assertIn("?g=1", url)
        status, data, hdr = self.call(url)
        self.assertEqual((status, hdr["Content-Type"]), (200, "image/jpeg"))
        self.call("/api/source", {"kind": "local", "path": str(self.photos)})
        self.assertIn("?g=2", json.loads(self.call("/api/images")[1])["images"][0]["url"])

    def test_remote_images_are_cached_on_disk(self):
        self.connect("dropbox")
        self.assertEqual(self.call("/api/source", {"kind": "dropbox", "path": "/Photos"})[0], 200)
        self.call("/img/1?g=1"); self.call("/img/1?g=1")
        thumbs = [1 for _, p, _, _ in Mock.log if p == "/2/files/get_thumbnail_v2"]
        self.assertEqual(len(thumbs), 1)

    def test_not_connected_returns_401_with_provider(self):
        status, data, _ = self.call("/api/source", {"kind": "gdrive"})
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(data)["auth"], "gdrive")

    def test_unknown_kind_and_bad_index(self):
        self.assertEqual(self.call("/api/source", {"kind": "ftp"})[0], 400)
        self.call("/api/source", {"kind": "local", "path": str(self.photos)})
        self.assertEqual(self.call("/img/99?g=1")[0], 404)

    def test_foreign_host_and_origin_rejected(self):
        self.assertEqual(self.call("/api/state", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.call("/api/source", {"kind": "local", "path": "/"},
                                   headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.call("/api/state")[0], 200)

    def test_state_never_leaks_tokens(self):
        self.connect("gdrive")
        _, data, _ = self.call("/api/state")
        self.assertNotIn(b"tok-gdrive", data)
        self.assertTrue(json.loads(data)["connected"]["gdrive"])

    def test_oauth_start_redirects_to_provider(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k): return None
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(f"http://127.0.0.1:{self.port}/oauth/start/dropbox")
            self.fail("expected redirect")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertIn("dropbox.com/oauth2/authorize", e.headers["Location"])


if __name__ == "__main__":
    unittest.main()
