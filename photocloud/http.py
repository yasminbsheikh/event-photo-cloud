"""Tiny urllib wrapper (the project has no third-party dependencies)."""
import json
import urllib.error
import urllib.parse
import urllib.request

from .errors import SourceError


class ApiError(SourceError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"Remote service error {status}: {detail[:300]}")
        self.status = status
        self.detail = detail


def request(method: str, url: str, *, headers: dict | None = None, json_body=None,
            form: dict | None = None, timeout: float = 60) -> bytes:
    data = None
    hdrs = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode("utf-8", "replace")) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"Network problem talking to {urllib.parse.urlparse(url).netloc}: {exc}") from exc


def request_json(method: str, url: str, **kw) -> dict:
    body = request(method, url, **kw)
    try:
        return json.loads(body) if body else {}
    except ValueError as exc:
        raise SourceError("Unexpected (non-JSON) response from remote service.") from exc
